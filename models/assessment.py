from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .academic import require_role


class AcademicResult(models.Model):
    _inherit = ['student.result', 'university.academic.workflow']
    _name = 'student.result'

    registration_id = fields.Many2one('university.course.registration', ondelete='restrict', tracking=True)
    semester_id = fields.Many2one(related='registration_id.semester_id', store=True)
    lecturer_id = fields.Many2one(related='registration_id.lecturer_id', store=True)
    coordinator_id = fields.Many2one(related='registration_id.coordinator_id', store=True)
    policy_id = fields.Many2one(related='registration_id.policy_id', store=True)
    ca_mark = fields.Float(string='Continuous Assessment (%)', tracking=True)
    exam_mark = fields.Float(string='Examination (%)', tracking=True)
    ca_entered = fields.Boolean(readonly=True)
    exam_entered = fields.Boolean(readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('submitted', 'Submitted'), ('moderated', 'Moderated'), ('approved', 'Board Approved'), ('published', 'Published')], default='draft', required=True, tracking=True)
    moderation_note = fields.Text()
    amendment_reason = fields.Text()
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)
    published_by = fields.Many2one('res.users', readonly=True, copy=False)
    published_on = fields.Datetime(readonly=True, copy=False)
    revision = fields.Integer(default=1, readonly=True)

    _sql_constraints = [('registration_result', 'unique(registration_id)', 'Only one result record is allowed per course registration.')]

    @api.depends('marks', 'policy_id')
    def _compute_grade(self):
        legacy = self.filtered(lambda r: not r.policy_id)
        super(AcademicResult, legacy)._compute_grade()
        for r in self - legacy:
            r.grade, r.grade_point = r.policy_id._grade(r.marks)
            r.status = 'pass' if r.marks >= r.policy_id.pass_mark else 'fail'

    @api.constrains('ca_mark', 'exam_mark', 'registration_id', 'student_id', 'course_id', 'credit_units')
    def _check_assessment(self):
        for r in self:
            if not 0 <= r.ca_mark <= 100 or not 0 <= r.exam_mark <= 100:
                raise ValidationError('Assessment marks must be between 0 and 100.')
            if r.registration_id:
                reg = r.registration_id
                if reg.state != 'approved' or r.student_id != reg.student_id or r.course_id != reg.course_id or r.credit_units != reg.credit_units:
                    raise ValidationError('Results must match the approved student course registration and credits.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if {'ca_entered', 'exam_entered', 'revision'} & set(vals):
                raise AccessError('Assessment entry flags and revisions are system controlled.')
            reg = self.env['university.course.registration'].browse(vals.get('registration_id'))
            if reg:
                vals.update(student_id=reg.student_id.id, course_id=reg.course_id.id,
                            credit_units=reg.credit_units, university_id=reg.student_id.university_id.id)
                vals['ca_entered'] = 'ca_mark' in vals
                vals['exam_entered'] = 'exam_mark' in vals
                vals['marks'] = ((vals.get('ca_mark', 0) * reg.policy_id.ca_weight) + (vals.get('exam_mark', 0) * reg.policy_id.exam_weight)) / 100
        records = super().create(vals_list)
        for record in records:
            record._audit('Initial assessment marks', 'CA %s; exam %s; final %s' % (record.ca_mark, record.exam_mark, record.marks))
        return records

    def write(self, vals):
        if {'ca_entered', 'exam_entered', 'revision'} & set(vals):
            raise AccessError('Assessment entry flags and revisions are system controlled.')
        if any(r.state != 'draft' for r in self) and set(vals) - {'moderation_note', 'amendment_reason'}:
            raise UserError('Reopen the result with an authorized amendment reason before changing marks.')
        if set(vals) & {'moderation_note', 'amendment_reason'}:
            require_role(self.env, 'group_coordinator', 'group_exam_board', 'group_registrar')
        if 'registration_id' in vals and any(r.registration_id for r in self):
            raise UserError('A linked result cannot be reassigned to another registration.')
        for r in self:
            update = dict(vals)
            reg = self.env['university.course.registration'].browse(vals.get('registration_id')) if 'registration_id' in vals else r.registration_id
            if reg:
                if 'marks' in vals:
                    raise UserError('Enter assessment components; the final mark is calculated from the approved policy.')
                if 'registration_id' in vals:
                    update.update(student_id=reg.student_id.id, course_id=reg.course_id.id,
                                  credit_units=reg.credit_units, university_id=reg.student_id.university_id.id)
                if 'ca_mark' in vals or 'exam_mark' in vals or 'registration_id' in vals:
                    update['marks'] = (vals.get('ca_mark', r.ca_mark) * reg.policy_id.ca_weight + vals.get('exam_mark', r.exam_mark) * reg.policy_id.exam_weight) / 100
                    if 'ca_mark' in vals:
                        update['ca_entered'] = True
                    if 'exam_mark' in vals:
                        update['exam_entered'] = True
                    r._audit('Assessment marks changed', 'CA %s -> %s; exam %s -> %s; final %s -> %s; %s' % (r.ca_mark, vals.get('ca_mark', r.ca_mark), r.exam_mark, vals.get('exam_mark', r.exam_mark), r.marks, update['marks'], r.amendment_reason or 'Initial draft entry'))
            super(AcademicResult, r).write(update)
        return True

    def action_submit(self):
        require_role(self.env, 'group_lecturer', 'group_coordinator', 'group_registrar')
        for r in self:
            if r.state != 'draft' or not r.registration_id or not r.ca_entered or not r.exam_entered:
                raise UserError('Link an approved registration and enter both assessment components before submission.')
            if not r.registration_id.attendance_count or r.registration_id.absence_flag:
                raise UserError('The student has not met the approved attendance requirement.')
            r._controlled_write({'state': 'submitted'}, 'Assessment submitted', 'CA %s, exam %s, final %s; policy %s v%s' % (r.ca_mark, r.exam_mark, r.marks, r.policy_id.name, r.policy_id.version))
        return True

    def action_moderate(self):
        require_role(self.env, 'group_coordinator', 'group_registrar')
        if any(r.state != 'submitted' or not r.moderation_note for r in self):
            raise UserError('Record moderation notes on submitted results before moderation.')
        return self._controlled_write({'state': 'moderated'}, 'Department moderation completed', self.mapped('moderation_note'))

    def action_approve(self):
        require_role(self.env, 'group_exam_board')
        for r in self:
            if r.state != 'moderated':
                raise UserError('The department must moderate results before examination board approval.')
            registrations = r.registration_id.offering_id.registration_ids.filtered(lambda reg: reg.state == 'approved')
            if any(not reg.result_ids or reg.result_ids.state not in ('moderated', 'approved', 'published') for reg in registrations):
                raise UserError('Every approved class registration must have a moderated result before board approval.')
            r._controlled_write({'state': 'approved', 'approved_by': self.env.uid, 'approved_on': fields.Datetime.now()}, 'Examination board approved')
        return True

    def action_publish(self):
        require_role(self.env, 'group_registrar')
        if any(r.state != 'approved' for r in self):
            raise UserError('Only examination-board-approved results may be published.')
        return self._controlled_write({'state': 'published', 'published_by': self.env.uid, 'published_on': fields.Datetime.now()}, 'Results published')

    def action_reopen(self):
        require_role(self.env, 'group_exam_board', 'group_registrar')
        for r in self:
            if r.state == 'draft' or not (r.amendment_reason or '').strip():
                raise UserError('An amendment reason is required to reopen a submitted or final result.')
            if r.student_id.registration_state == 'graduated':
                raise UserError('Results for a graduated student require a formal graduation revocation process before amendment.')
            reviews = self.env['university.progression'].sudo().search([('student_id', '=', r.student_id.id), ('semester_id', '=', r.semester_id.id), ('state', '!=', 'draft')])
            reviews._controlled_write({'state': 'draft', 'decision': False, 'approved_by': False, 'approved_on': False}, 'Progression invalidated by result amendment', r.amendment_reason)
            clearances = self.env['university.student.clearance'].sudo().search([('student_id', '=', r.student_id.id), ('kind', '=', 'academic'), ('state', '=', 'cleared')])
            clearances._controlled_write({'state': 'draft', 'approved_by': False, 'approved_on': False}, 'Academic clearance invalidated', r.amendment_reason)
            r._controlled_write({'state': 'draft', 'revision': r.revision + 1, 'approved_by': False,
                                 'approved_on': False, 'published_by': False, 'published_on': False},
                                'Result reopened', '%s; previous final mark %s' % (r.amendment_reason, r.marks))
        return True


class AcademicProgression(models.Model):
    _name = 'university.progression'
    _description = 'Student Academic Progression Review'
    _inherit = ['university.academic.workflow']
    _rec_name = 'student_id'

    student_id = fields.Many2one('student.university', required=True, ondelete='restrict')
    semester_id = fields.Many2one('university.semester', required=True, ondelete='restrict')
    coordinator_id = fields.Many2one(related='student_id.programme_id.coordinator_id', store=True)
    policy_id = fields.Many2one('university.academic.policy', required=True, ondelete='restrict', domain=[('state', '=', 'approved')])
    state = fields.Selection([('draft', 'Draft'), ('evaluated', 'Evaluated'), ('approved', 'Approved')], default='draft', required=True, copy=False)
    decision = fields.Selection([('progress', 'Progress'), ('repeat', 'Repeat / Academic Support')], readonly=True)
    earned_credits = fields.Integer(readonly=True)
    failed_courses = fields.Integer(readonly=True)
    gpa = fields.Float(readonly=True)
    evaluation_notes = fields.Text(readonly=True)
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [('unique_progression', 'unique(student_id,semester_id)', 'A progression decision already exists for this semester.')]

    def write(self, vals):
        if set(vals) & {'decision', 'earned_credits', 'failed_courses', 'gpa', 'evaluation_notes'} or any(r.state != 'draft' for r in self):
            raise UserError('Use evaluation and approval actions; progression snapshots cannot be edited.')
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if set(vals) & {'decision', 'earned_credits', 'failed_courses', 'gpa', 'evaluation_notes'}:
                raise AccessError('Progression results are computed by evaluation.')
        return super().create(vals_list)

    def _evaluation(self):
        self.ensure_one()
        registrations = self.env['university.course.registration'].sudo().search([('student_id', '=', self.student_id.id), ('semester_id', '=', self.semester_id.id), ('state', '=', 'approved')])
        if self.policy_id.state != 'approved' or not registrations:
            raise UserError('An approved policy and course registrations are required for progression.')
        if any(not reg.result_ids or reg.result_ids.state != 'published' for reg in registrations):
            raise UserError('All semester results must be published before progression review.')
        if self.env['university.academic.appeal'].sudo().search_count([('student_id', '=', self.student_id.id), ('result_id', 'in', registrations.result_ids.ids), ('state', '=', 'draft')]):
            raise UserError('Resolve open result appeals before progression approval.')
        results = registrations.result_ids
        credits = sum(results.filtered(lambda r: r.status == 'pass').mapped('credit_units'))
        failed = len(results.filtered(lambda r: r.status == 'fail'))
        total = sum(results.mapped('credit_units'))
        gpa = sum(r.grade_point * r.credit_units for r in results) / total if total else 0
        decision = 'progress' if credits >= self.policy_id.minimum_progression_credits and failed <= self.policy_id.maximum_failed_courses and gpa >= self.policy_id.minimum_gpa else 'repeat'
        return {'earned_credits': credits, 'failed_courses': failed, 'gpa': gpa, 'decision': decision,
                'evaluation_notes': 'Policy %s v%s; %s published results; failed courses %s. Repeat attempts: %s.' % (self.policy_id.name, self.policy_id.version, len(results), failed, ', '.join('%s:%s' % (reg.course_id.code, reg.attempt_number) for reg in registrations))}

    def action_evaluate(self):
        require_role(self.env, 'group_coordinator', 'group_registrar')
        for r in self:
            if r.state != 'draft':
                raise UserError('Evaluate a draft progression review.')
            values = r._evaluation()
            values['state'] = 'evaluated'
            r._controlled_write(values, 'Progression evaluated', values['evaluation_notes'])
        return True

    def action_approve(self):
        require_role(self.env, 'group_exam_board', 'group_registrar')
        for r in self:
            if r.state != 'evaluated':
                raise UserError('Evaluate progression before approval.')
            values = r._evaluation()
            values.update(state='approved', approved_by=self.env.uid, approved_on=fields.Datetime.now())
            r._controlled_write(values, 'Progression approved', values['evaluation_notes'])
        return True


class StudentClearance(models.Model):
    _name = 'university.student.clearance'
    _description = 'Separate Student Graduation Clearance'
    _inherit = ['university.academic.workflow']
    _rec_name = 'student_id'

    student_id = fields.Many2one('student.university', required=True, ondelete='restrict')
    kind = fields.Selection([('academic', 'Academic'), ('financial', 'Financial'), ('library', 'Library')], required=True)
    state = fields.Selection([('draft', 'Pending'), ('cleared', 'Cleared'), ('blocked', 'Blocked')], default='draft', required=True, copy=False)
    notes = fields.Text(required=True)
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [('unique_student_clearance', 'unique(student_id,kind)', 'A clearance already exists for this student and department.')]

    def _check_officer(self):
        for r in self:
            require_role(self.env, {'academic': 'group_registrar', 'financial': 'group_finance_officer', 'library': 'group_library_officer'}[r.kind])

    def write(self, vals):
        self._check_officer()
        if set(vals) - {'notes'}:
            raise UserError('A clearance cannot be reassigned. Use the decision actions.')
        return super().write(vals)

    def action_clear(self):
        self._check_officer()
        for r in self:
            if not r.notes.strip():
                raise UserError('Clearance evidence and notes are required.')
            if r.kind == 'academic':
                r.student_id._graduation_academics()
            if r.kind == 'financial' and r.student_id.fee_balance > 0:
                raise UserError('Outstanding student fees prevent financial clearance.')
            r._controlled_write({'state': 'cleared', 'approved_by': self.env.uid, 'approved_on': fields.Datetime.now()}, 'Clearance granted', r.notes)
        return True

    def action_block(self):
        self._check_officer()
        return self._controlled_write({'state': 'blocked', 'approved_by': self.env.uid, 'approved_on': fields.Datetime.now()}, 'Clearance blocked', self.mapped('notes'))
