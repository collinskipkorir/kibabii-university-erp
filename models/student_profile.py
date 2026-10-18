from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .academic import MODULE, require_role


class StudentProfile(models.Model):
    _inherit = ['student.university', 'university.academic.workflow']
    _name = 'student.university'

    photo = fields.Image(max_width=1024, max_height=1024)
    date_of_birth = fields.Date()
    nationality_id = fields.Many2one('res.country', string='Nationality')
    identity_type = fields.Selection([('national_id', 'National ID'), ('passport', 'Passport'), ('birth_certificate', 'Birth Certificate')])
    identity_number = fields.Char(copy=False, groups=MODULE + '.group_registrar,' + MODULE + '.group_university_manager')
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one('res.country.state', string='County / State')
    country_id = fields.Many2one('res.country')
    postal_code = fields.Char()
    guardian_name = fields.Char()
    guardian_relationship = fields.Char()
    guardian_phone = fields.Char()
    guardian_email = fields.Char()
    emergency_name = fields.Char()
    emergency_relationship = fields.Char()
    emergency_phone = fields.Char()
    previous_school = fields.Char()
    entry_qualification = fields.Char()
    qualification_year = fields.Integer()
    sponsor_name = fields.Char()
    sponsor_contact = fields.Char()
    support_requirements = fields.Text(groups=MODULE + '.group_registrar,' + MODULE + '.group_university_manager')
    programme_id = fields.Many2one('university.programme', ondelete='restrict', tracking=True)
    department_id = fields.Many2one(related='programme_id.department_id', store=True)
    academic_year_id = fields.Many2one('university.academic.year', ondelete='restrict')
    intake = fields.Char()
    study_mode = fields.Selection([('full_time', 'Full Time'), ('part_time', 'Part Time'), ('distance', 'Distance Learning')], default='full_time')
    year_of_study = fields.Integer(default=1)
    registration_state = fields.Selection([('applicant', 'Applicant'), ('submitted', 'Submitted'), ('verified', 'Verified'), ('admitted', 'Admitted'), ('registered', 'Registered'), ('suspended', 'Suspended'), ('rejected', 'Rejected'), ('graduated', 'Graduated')], default='applicant', required=True, tracking=True)
    admission_number = fields.Char(readonly=True, copy=False)
    decision_reason = fields.Text()
    admission_by = fields.Many2one('res.users', readonly=True, copy=False)
    admission_on = fields.Datetime(readonly=True, copy=False)
    registration_confirmed_by = fields.Many2one('res.users', readonly=True, copy=False)
    registration_confirmed_on = fields.Datetime(readonly=True, copy=False)
    graduation_by = fields.Many2one('res.users', readonly=True, copy=False)
    graduation_on = fields.Datetime(readonly=True, copy=False)
    document_ids = fields.One2many('university.student.document', 'student_id')
    registration_ids = fields.One2many('university.course.registration', 'student_id')
    clearance_ids = fields.One2many('university.student.clearance', 'student_id')
    progression_ids = fields.One2many('university.progression', 'student_id')
    published_result_ids = fields.One2many('student.result', 'student_id', domain=[('state', '=', 'published')])
    published_credits = fields.Integer(compute='_compute_published_progress')
    published_gpa = fields.Float(compute='_compute_published_progress')
    graduation_eligible = fields.Boolean(compute='_compute_graduation_eligible')
    graduation_blockers = fields.Text(compute='_compute_graduation_eligible')
    academic_cleared = fields.Boolean(compute='_compute_graduation_eligible')
    financial_cleared = fields.Boolean(compute='_compute_graduation_eligible')
    library_cleared = fields.Boolean(compute='_compute_graduation_eligible')

    _sql_constraints = [('unique_portal_student', 'unique(user_id)', 'A portal user can be linked to only one student.'), ('unique_admission_number', 'unique(admission_number)', 'Admission numbers must be unique.'), ('unique_student_email', 'unique(email)', 'A student with this email already exists.'), ('unique_student_identity', 'unique(identity_number)', 'A student with this identity number already exists.')]

    @api.depends('result_ids.state', 'result_ids.grade_point', 'result_ids.credit_units', 'result_ids.status')
    def _compute_published_progress(self):
        for r in self:
            results = r.result_ids.filtered(lambda res: res.state == 'published')
            # Repeated courses count once, using the highest published mark.
            best = {}
            for result in results:
                if result.course_id.id not in best or result.marks > best[result.course_id.id].marks:
                    best[result.course_id.id] = result
            credits = sum(res.credit_units for res in best.values())
            r.published_credits = sum(res.credit_units for res in best.values() if res.status == 'pass')
            r.published_gpa = sum(res.grade_point * res.credit_units for res in best.values()) / credits if credits else 0

    @api.depends('registration_state', 'published_credits', 'published_gpa', 'fee_balance', 'clearance_ids.state', 'programme_id')
    def _compute_graduation_eligible(self):
        for r in self:
            clearances = r.sudo().clearance_ids.filtered(lambda c: c.state == 'cleared').mapped('kind')
            r.academic_cleared = 'academic' in clearances
            r.financial_cleared = 'financial' in clearances
            r.library_cleared = 'library' in clearances
            try:
                r._check_graduation()
                r.graduation_eligible = True
                r.graduation_blockers = False
            except (UserError, ValidationError) as error:
                r.graduation_eligible = False
                r.graduation_blockers = str(error)

    @api.constrains('date_of_birth', 'year_of_study', 'programme_id', 'university_id', 'identity_number', 'user_id')
    def _check_profile(self):
        for r in self:
            if r.date_of_birth and r.date_of_birth >= fields.Date.context_today(r):
                raise ValidationError('Date of birth must be in the past.')
            if r.year_of_study < 1:
                raise ValidationError('Year of study must be positive.')
            if r.programme_id and r.programme_id.university_id != r.university_id:
                raise ValidationError('The programme must belong to the student university.')
            if r.sudo().identity_number and self.sudo().search_count([('identity_number', '=', r.sudo().identity_number.strip()), ('id', '!=', r.id)]):
                raise ValidationError('A student with this identity number already exists.')
            if r.user_id and not r.user_id.has_group(MODULE + '.group_student'):
                raise ValidationError('The linked user must have the Student portal role.')

    @api.model_create_multi
    def create(self, vals_list):
        protected = {'admission_number', 'admission_by', 'admission_on', 'registration_confirmed_by', 'registration_confirmed_on', 'graduation_by', 'graduation_on'}
        for vals in vals_list:
            if protected.intersection(vals) or vals.get('registration_state', 'applicant') != 'applicant':
                raise AccessError('Create an applicant and use the registration workflow.')
            if vals.get('email'):
                vals['email'] = vals['email'].strip().lower()
            if vals.get('identity_number'):
                vals['identity_number'] = vals['identity_number'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get('email'):
            vals['email'] = vals['email'].strip().lower()
        if vals.get('identity_number'):
            vals['identity_number'] = vals['identity_number'].strip().upper()
        protected = {'registration_state', 'admission_number', 'admission_by', 'admission_on', 'registration_confirmed_by', 'registration_confirmed_on', 'graduation_by', 'graduation_on'}
        if protected.intersection(vals):
            raise AccessError('Use student admission and registration actions to change status.')
        if {'programme_id', 'university_id', 'user_id'} & set(vals) and any(r.registration_ids.filtered(lambda reg: reg.state == 'approved') for r in self):
            raise UserError('Students with approved course registrations cannot be reassigned to another identity or programme.')
        return super().write(vals)

    def unlink(self):
        if any(r.registration_state != 'applicant' or r.registration_ids or r.result_ids or r.fee_ids for r in self):
            raise UserError('Retain student records after admission or academic/financial activity.')
        return super().unlink()

    def _check_complete(self):
        for r in self:
            required = ['date_of_birth', 'nationality_id', 'programme_id', 'academic_year_id', 'intake', 'study_mode', 'emergency_name', 'emergency_phone', 'entry_qualification']
            missing = [r._fields[name].string for name in required if not r[name]]
            if not r.sudo().identity_number:
                missing.append('Identity Number')
            if missing:
                raise ValidationError('Complete the student profile: ' + ', '.join(missing))

    def action_submit_application(self):
        require_role(self.env, 'group_registrar')
        if any(r.registration_state != 'applicant' for r in self):
            raise UserError('Only applicant records can be submitted.')
        self._check_complete()
        for r in self:
            if not {'identity', 'qualification'}.issubset(set(r.document_ids.mapped('kind'))):
                raise UserError('Upload identity and qualification documents before submitting the application.')
        return self._controlled_write({'registration_state': 'submitted'}, 'Application submitted')

    def action_verify_application(self):
        require_role(self.env, 'group_registrar')
        for r in self:
            if r.registration_state != 'submitted':
                raise UserError('Submit the application before verification.')
            r._check_complete()
            verified = r.document_ids.filtered(lambda doc: doc.state == 'verified').mapped('kind')
            if not {'identity', 'qualification'}.issubset(set(verified)):
                raise UserError('Verify identity and qualification documents before admission.')
        return self._controlled_write({'registration_state': 'verified'}, 'Application verified')

    def action_admit(self):
        require_role(self.env, 'group_registrar')
        for r in self:
            if r.registration_state != 'verified':
                raise UserError('Verify eligibility and documents before admission approval.')
            r._controlled_write({'registration_state': 'admitted', 'admission_by': self.env.uid, 'admission_on': fields.Datetime.now(),
                                 'admission_number': self.env['ir.sequence'].next_by_code('university.student.admission')}, 'Admission approved')
        return True

    def action_confirm_registration(self):
        require_role(self.env, 'group_registrar')
        for r in self:
            if r.registration_state != 'admitted':
                raise UserError('Only an admitted student can be registered.')
            r._check_complete()
            verified = r.document_ids.filtered(lambda doc: doc.state == 'verified').mapped('kind')
            if not {'identity', 'qualification'}.issubset(set(verified)):
                raise UserError('Required documents must remain verified.')
        return self._controlled_write({'registration_state': 'registered', 'registration_confirmed_by': self.env.uid,
                                       'registration_confirmed_on': fields.Datetime.now(), 'date_of_admission': fields.Date.context_today(self)}, 'Registration confirmed')

    def action_return_application(self):
        require_role(self.env, 'group_registrar')
        if any(r.registration_state not in ('submitted', 'verified') or not r.decision_reason for r in self):
            raise UserError('Return a submitted application with a correction reason.')
        return self._controlled_write({'registration_state': 'applicant'}, 'Application returned for correction', self.mapped('decision_reason'))

    def action_reject_application(self):
        require_role(self.env, 'group_registrar')
        if any(r.registration_state not in ('submitted', 'verified') or not r.decision_reason for r in self):
            raise UserError('Record a reason before rejecting a submitted application.')
        return self._controlled_write({'registration_state': 'rejected'}, 'Admission rejected', self.mapped('decision_reason'))

    def action_suspend(self):
        require_role(self.env, 'group_registrar')
        if any(r.registration_state != 'registered' or not r.decision_reason for r in self):
            raise UserError('Suspend a registered student with a documented reason.')
        return self._controlled_write({'registration_state': 'suspended'}, 'Student suspended', self.mapped('decision_reason'))

    def action_reinstate(self):
        require_role(self.env, 'group_registrar')
        if any(r.registration_state != 'suspended' or not r.decision_reason for r in self):
            raise UserError('Reinstate a suspended student with a documented reason.')
        return self._controlled_write({'registration_state': 'registered'}, 'Student reinstated', self.mapped('decision_reason'))

    def _graduation_academics(self):
        self.ensure_one()
        programme = self.programme_id
        if not programme or self.published_credits < programme.required_credits or self.published_gpa < programme.policy_id.minimum_gpa:
            raise UserError('Programme credits and minimum GPA have not been met.')
        passed = self.result_ids.filtered(lambda r: r.state == 'published' and r.status == 'pass').mapped('course_id')
        if programme.course_ids - passed:
            raise UserError('All required programme courses must have a published passing result.')
        if self.env['university.course.registration'].sudo().search_count([('student_id', '=', self.id), ('state', '=', 'submitted')]):
            raise UserError('Resolve pending course registrations before graduation.')
        if self.env['university.academic.appeal'].sudo().search_count([('student_id', '=', self.id), ('state', '=', 'draft')]):
            raise UserError('Resolve open academic appeals before graduation.')
        registrations = self.registration_ids.filtered(lambda r: r.state == 'approved')
        if any(not reg.result_ids or reg.result_ids.state != 'published' for reg in registrations):
            raise UserError('Publish all approved course results before graduation.')
        semesters = registrations.mapped('semester_id')
        approved = self.progression_ids.filtered(lambda p: p.state == 'approved' and p.decision == 'progress').mapped('semester_id')
        if semesters - approved:
            raise UserError('Approve progression for every registered semester before graduation.')
        return True

    def _check_graduation(self):
        self.ensure_one()
        if self.registration_state not in ('registered', 'graduated'):
            raise UserError('Only registered students can graduate.')
        self._graduation_academics()
        clearances = self.sudo().clearance_ids.filtered(lambda c: c.state == 'cleared').mapped('kind')
        if not {'academic', 'financial', 'library'}.issubset(set(clearances)) or self.fee_balance > 0:
            raise UserError('Separate academic, financial and library clearances are required, with no outstanding fees.')
        return True

    def action_graduate(self):
        require_role(self.env, 'group_registrar')
        for r in self:
            if r.registration_state == 'graduated':
                raise UserError('This student has already graduated.')
            r._check_graduation()
        return self._controlled_write({'registration_state': 'graduated', 'graduation_by': self.env.uid,
                                       'graduation_on': fields.Datetime.now()}, 'Graduation authorized')


class StudentDocument(models.Model):
    _name = 'university.student.document'
    _description = 'Student Supporting Document'
    _inherit = ['university.academic.workflow']

    name = fields.Char(required=True)
    student_id = fields.Many2one('student.university', required=True, ondelete='restrict')
    kind = fields.Selection([('identity', 'Identity'), ('qualification', 'Qualification'), ('photo', 'Photograph'), ('other', 'Other')], required=True)
    filename = fields.Char(required=True)
    file_data = fields.Binary(required=True, attachment=False)
    state = fields.Selection([('draft', 'Pending Verification'), ('verified', 'Verified'), ('rejected', 'Rejected')], default='draft', required=True, copy=False)
    notes = fields.Text()
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)

    def write(self, vals):
        if any(r.state != 'draft' for r in self):
            raise UserError('Verified or rejected evidence is immutable; upload a replacement document.')
        if 'student_id' in vals:
            raise UserError('A document cannot be moved to another student.')
        return super().write(vals)

    def action_verify(self):
        require_role(self.env, 'group_registrar')
        if any(r.state != 'draft' for r in self):
            raise UserError('Only pending documents can be verified.')
        return self._controlled_write({'state': 'verified', 'approved_by': self.env.uid, 'approved_on': fields.Datetime.now()}, 'Document verified')

    def action_reject(self):
        require_role(self.env, 'group_registrar')
        if any(r.state != 'draft' or not r.notes for r in self):
            raise UserError('Record a rejection reason on the pending document.')
        return self._controlled_write({'state': 'rejected', 'approved_by': self.env.uid, 'approved_on': fields.Datetime.now()}, 'Document rejected', self.mapped('notes'))
