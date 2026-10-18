from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

MODULE = 'kibabii-university-erp'


def require_role(env, *roles):
    if not env.su and not any(env.user.has_group(MODULE + '.' + role) for role in ('group_university_manager',) + roles):
        raise AccessError('You are not authorized to perform this academic action.')


class AcademicAudit(models.Model):
    _name = 'university.academic.audit'
    _description = 'Academic Audit History'
    _order = 'create_date desc, id desc'

    model_name = fields.Char(required=True, readonly=True)
    record_id = fields.Integer(required=True, readonly=True)
    record_name = fields.Char(readonly=True)
    action = fields.Char(required=True, readonly=True)
    details = fields.Text(readonly=True)
    actor_id = fields.Many2one('res.users', readonly=True, copy=False)

    def write(self, vals):
        raise AccessError('Academic audit entries cannot be edited.')

    def unlink(self):
        raise AccessError('Academic audit entries cannot be deleted.')


class AcademicWorkflow(models.AbstractModel):
    _name = 'university.academic.workflow'
    _description = 'Controlled Academic Workflow'

    def _audit(self, action, details=''):
        for record in self:
            self.env['university.academic.audit'].sudo().create({
                'model_name': record._name, 'record_id': record.id,
                'record_name': record.display_name, 'action': action,
                'details': str(details), 'actor_id': self.env.uid,
            })

    def _controlled_write(self, vals, action, reason=''):
        # Private methods are not RPC callable. State changes never depend on client context flags.
        result = super(AcademicWorkflow, self).write(vals)
        self._audit(action, reason)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        default_state = self.default_get(['state']).get('state') if 'state' in self._fields else None
        protected = {'approved_by', 'approved_on', 'published_by', 'published_on', 'confirmed_by', 'confirmed_on'}
        for vals in vals_list:
            if ('state' in vals and vals['state'] != default_state) or protected.intersection(vals):
                raise AccessError('Create a draft record and use the approval actions.')
        records = super().create(vals_list)
        records._audit('Created')
        return records

    def write(self, vals):
        protected = {'state', 'approved_by', 'approved_on', 'published_by', 'published_on', 'confirmed_by', 'confirmed_on'}
        if protected.intersection(vals):
            raise AccessError('Use the workflow actions to change approval status.')
        result = super().write(vals)
        if vals:
            self._audit('Updated', ', '.join(sorted(vals)))
        return result

    def unlink(self):
        if 'state' in self._fields and any(r.state != 'draft' for r in self):
            raise UserError('Only drafts can be deleted. Retain approved records for audit.')
        return super().unlink()


class AcademicYear(models.Model):
    _name = 'university.academic.year'
    _description = 'Academic Year'
    _order = 'date_start desc'

    name = fields.Char(required=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [('year_dates', 'CHECK(date_end >= date_start)', 'Academic year end must follow its start.')]


class AcademicSemester(models.Model):
    _name = 'university.semester'
    _description = 'Academic Semester'
    _order = 'date_start desc'

    name = fields.Char(required=True)
    year_id = fields.Many2one('university.academic.year', required=True, ondelete='restrict')
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    registration_start = fields.Date(required=True)
    registration_end = fields.Date(required=True)

    @api.constrains('date_start', 'date_end', 'registration_start', 'registration_end', 'year_id')
    def _check_dates(self):
        for r in self:
            if not (r.year_id.date_start <= r.date_start <= r.date_end <= r.year_id.date_end):
                raise ValidationError('Semester dates must be within the academic year.')
            if r.registration_end < r.registration_start or r.registration_end > r.date_end:
                raise ValidationError('Check the semester registration window.')


class AcademicPolicy(models.Model):
    _name = 'university.academic.policy'
    _description = 'Versioned Academic Policy'
    _inherit = ['university.academic.workflow']

    name = fields.Char(required=True)
    version = fields.Char(required=True, default='1')
    state = fields.Selection([('draft', 'Draft'), ('approved', 'Approved')], default='draft', required=True, copy=False)
    ca_weight = fields.Float(default=30, required=True)
    exam_weight = fields.Float(default=70, required=True)
    pass_mark = fields.Float(default=40, required=True)
    a_min = fields.Float(default=70, required=True)
    b_min = fields.Float(default=60, required=True)
    c_min = fields.Float(default=50, required=True)
    d_min = fields.Float(default=40, required=True)
    a_points = fields.Float(default=4)
    b_points = fields.Float(default=3)
    c_points = fields.Float(default=2)
    d_points = fields.Float(default=1)
    minimum_attendance = fields.Float(default=75)
    minimum_progression_credits = fields.Integer(default=3)
    minimum_gpa = fields.Float(default=2)
    maximum_failed_courses = fields.Integer(default=0)
    maximum_repeat_attempts = fields.Integer(default=3)
    appeal_days = fields.Integer(default=14)
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [('policy_version', 'unique(name,version)', 'This policy version already exists.')]

    @api.constrains('ca_weight', 'exam_weight', 'pass_mark', 'a_min', 'b_min', 'c_min', 'd_min', 'minimum_attendance', 'minimum_gpa', 'maximum_failed_courses', 'minimum_progression_credits', 'maximum_repeat_attempts', 'appeal_days', 'a_points', 'b_points', 'c_points', 'd_points')
    def _check_policy(self):
        for r in self:
            if abs(r.ca_weight + r.exam_weight - 100) > 0.001 or min(r.ca_weight, r.exam_weight) < 0:
                raise ValidationError('Assessment weights must be nonnegative and total 100%.')
            if not 100 >= r.a_min > r.b_min > r.c_min > r.d_min >= 0 or not 0 <= r.pass_mark <= 100:
                raise ValidationError('Grade thresholds must descend from A to D, within 0–100.')
            if not 0 <= r.minimum_attendance <= 100 or min(r.minimum_gpa, r.maximum_failed_courses, r.minimum_progression_credits, r.appeal_days) < 0 or r.maximum_repeat_attempts < 1:
                raise ValidationError('Check attendance and progression policy limits.')
            if not r.a_points >= r.b_points >= r.c_points >= r.d_points >= 0 or r.minimum_gpa > r.a_points:
                raise ValidationError('Grade points must descend and the minimum GPA must be attainable.')

    def write(self, vals):
        if any(r.state == 'approved' for r in self):
            raise UserError('Approved policies are immutable. Duplicate the policy and increment its version.')
        return super().write(vals)

    def copy(self, default=None):
        self.ensure_one()
        values = dict(default or {})
        values.setdefault('state', 'draft')
        values.setdefault('version', str(int(self.version) + 1) if self.version.isdigit() else self.version + '-copy')
        return super().copy(values)

    def action_approve(self):
        require_role(self.env, 'group_registrar', 'group_exam_board')
        if any(r.state != 'draft' for r in self):
            raise UserError('Only draft policies can be approved.')
        return self._controlled_write({'state': 'approved', 'approved_by': self.env.uid, 'approved_on': fields.Datetime.now()}, 'Policy approved')

    def _grade(self, mark):
        self.ensure_one()
        for letter in 'abcd':
            if mark >= self[letter + '_min']:
                return letter.upper(), self[letter + '_points']
        return 'F', 0.0


class AcademicProgramme(models.Model):
    _name = 'university.programme'
    _description = 'Academic Programme'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    department_id = fields.Many2one('university.department', required=True, ondelete='restrict')
    university_id = fields.Many2one(related='department_id.university_id', store=True)
    coordinator_id = fields.Many2one('res.users', required=True)
    required_credits = fields.Integer(required=True, default=120)
    duration_years = fields.Integer(default=4)
    course_ids = fields.Many2many('university.course', string='Required Courses')
    policy_id = fields.Many2one('university.academic.policy', required=True, ondelete='restrict', domain=[('state', '=', 'approved')])
    active = fields.Boolean(default=True)

    _sql_constraints = [('programme_code', 'unique(code)', 'Programme code must be unique.'), ('programme_credits', 'CHECK(required_credits > 0 AND duration_years > 0)', 'Credits and duration must be positive.')]

    @api.constrains('policy_id', 'course_ids', 'department_id')
    def _check_structure(self):
        for r in self:
            if r.policy_id.state != 'approved':
                raise ValidationError('Select an approved academic policy.')
            if any(c.university_id != r.university_id for c in r.course_ids):
                raise ValidationError('Programme courses must belong to the same university.')

    def write(self, vals):
        if {'policy_id', 'course_ids', 'required_credits', 'department_id'} & set(vals) and self.env['university.course.offering'].sudo().search_count([('programme_id', 'in', self.ids), ('state', '!=', 'draft')]):
            raise UserError('Keep the curriculum and policy stable after opening classes. Create a new programme version.')
        return super().write(vals)


class AcademicCourse(models.Model):
    _inherit = 'university.course'

    prerequisite_ids = fields.Many2many('university.course', 'university_course_prerequisite_rel', 'course_id', 'prerequisite_id', string='Prerequisites')

    def write(self, vals):
        if {'credit_units', 'prerequisite_ids', 'university_id'} & set(vals) and self.env['university.course.offering'].sudo().search_count([('course_id', 'in', self.ids), ('state', '!=', 'draft')]):
            raise UserError('Credits and prerequisites cannot change after a course is offered. Create a new course version.')
        return super().write(vals)

    @api.constrains('prerequisite_ids')
    def _check_prerequisites(self):
        def visit(course, path):
            if course.id in path:
                raise ValidationError('Course prerequisites cannot contain a cycle.')
            for prerequisite in course.prerequisite_ids:
                if prerequisite.university_id != course.university_id:
                    raise ValidationError('Prerequisites must belong to the same university.')
                visit(prerequisite, path | {course.id})
        for r in self:
            visit(r, set())


class CourseOffering(models.Model):
    _name = 'university.course.offering'
    _description = 'Semester Course Offering'
    _inherit = ['university.academic.workflow']

    name = fields.Char(compute='_compute_name', store=True)
    course_id = fields.Many2one('university.course', required=True, ondelete='restrict')
    programme_id = fields.Many2one('university.programme', required=True, ondelete='restrict')
    semester_id = fields.Many2one('university.semester', required=True, ondelete='restrict')
    lecturer_id = fields.Many2one('res.users', required=True)
    coordinator_id = fields.Many2one(related='programme_id.coordinator_id', store=True)
    policy_id = fields.Many2one('university.academic.policy', required=True, ondelete='restrict', domain=[('state', '=', 'approved')])
    capacity = fields.Integer(default=50, required=True)
    state = fields.Selection([('draft', 'Draft'), ('open', 'Registration Open'), ('closed', 'Closed')], default='draft', required=True, copy=False)
    registration_ids = fields.One2many('university.course.registration', 'offering_id')
    session_ids = fields.One2many('university.class.session', 'offering_id')

    _sql_constraints = [('unique_offering', 'unique(course_id,programme_id,semester_id)', 'This course is already offered for this programme and semester.'), ('positive_capacity', 'CHECK(capacity > 0)', 'Capacity must be positive.')]

    @api.onchange('programme_id')
    def _onchange_programme(self):
        if self.programme_id:
            self.policy_id = self.programme_id.policy_id

    @api.depends('course_id.name', 'semester_id.name', 'programme_id.code')
    def _compute_name(self):
        for r in self:
            r.name = '%s / %s / %s' % (r.course_id.name, r.semester_id.name, r.programme_id.code)

    @api.constrains('course_id', 'programme_id', 'policy_id', 'lecturer_id', 'capacity')
    def _check_offering(self):
        for r in self:
            if r.course_id not in r.programme_id.course_ids or r.policy_id.state != 'approved':
                raise ValidationError('Offer a programme course using an approved policy version.')
            if not r.lecturer_id.has_group(MODULE + '.group_lecturer'):
                raise ValidationError('The assigned lecturer must have the Lecturer role.')
            if self.env['university.course.registration'].sudo().search_count([('offering_id', '=', r.id), ('state', '=', 'approved')]) > r.capacity:
                raise ValidationError('Capacity cannot be less than the approved class size.')

    def write(self, vals):
        if any(r.state != 'draft' for r in self) and set(vals) - {'capacity'}:
            raise UserError('Academic assignments and policy cannot change after opening registration.')
        return super().write(vals)

    def action_open(self):
        require_role(self.env, 'group_registrar', 'group_coordinator')
        if any(r.state != 'draft' for r in self):
            raise UserError('Only draft offerings can be opened.')
        return self._controlled_write({'state': 'open'}, 'Registration opened')

    def action_close(self):
        require_role(self.env, 'group_registrar', 'group_coordinator')
        if any(r.state != 'open' for r in self):
            raise UserError('Only open offerings can be closed.')
        return self._controlled_write({'state': 'closed'}, 'Registration closed')


class CourseRegistration(models.Model):
    _name = 'university.course.registration'
    _description = 'Student Course Registration'
    _inherit = ['university.academic.workflow']
    _rec_name = 'student_id'

    student_id = fields.Many2one('student.university', required=True, ondelete='restrict')
    offering_id = fields.Many2one('university.course.offering', required=True, ondelete='restrict')
    course_id = fields.Many2one(related='offering_id.course_id', store=True)
    semester_id = fields.Many2one(related='offering_id.semester_id', store=True)
    lecturer_id = fields.Many2one(related='offering_id.lecturer_id', store=True)
    coordinator_id = fields.Many2one(related='offering_id.coordinator_id', store=True)
    policy_id = fields.Many2one(related='offering_id.policy_id', store=True)
    credit_units = fields.Integer(related='course_id.credit_units', store=True)
    state = fields.Selection([('draft', 'Draft'), ('submitted', 'Submitted'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('cancelled', 'Cancelled')], default='draft', required=True, copy=False)
    reason = fields.Text()
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)
    attendance_ids = fields.One2many('university.class.attendance', 'registration_id')
    result_ids = fields.One2many('student.result', 'registration_id')
    attendance_rate = fields.Float(compute='_compute_attendance')
    attendance_count = fields.Integer(compute='_compute_attendance')
    absence_flag = fields.Boolean(compute='_compute_attendance', search='_search_absence_flag')
    attempt_number = fields.Integer(compute='_compute_attempt')

    _sql_constraints = [('unique_registration', 'unique(student_id,offering_id)', 'This student already has a registration for this class.')]

    @api.depends('attendance_ids.status', 'attendance_ids.session_id.state', 'policy_id.minimum_attendance')
    def _compute_attendance(self):
        for r in self:
            lines = r.attendance_ids.filtered(lambda a: a.session_id.state == 'completed' and a.status != 'excused')
            r.attendance_count = len(lines)
            r.attendance_rate = 100.0 * len(lines.filtered(lambda a: a.status in ('present', 'late'))) / len(lines) if lines else 0
            r.absence_flag = bool(lines) and r.attendance_rate < r.policy_id.minimum_attendance

    def _compute_attempt(self):
        for r in self:
            r.attempt_number = self.sudo().search_count([('student_id', '=', r.student_id.id), ('course_id', '=', r.course_id.id), ('state', '=', 'approved')]) + (r.state != 'approved')

    def _search_absence_flag(self, operator, value):
        if operator not in ('=', '!='):
            raise UserError('Use equals or not equals for attendance warnings.')
        matching = self.search([('state', '=', 'approved')]).filtered(lambda r: r.absence_flag).ids
        return [('id', 'in' if (operator == '=') == bool(value) else 'not in', matching)]

    def write(self, vals):
        if any(r.state != 'draft' for r in self) and set(vals) - {'reason'}:
            raise UserError('Submitted registrations cannot be reassigned.')
        return super().write(vals)

    def _check_eligibility(self):
        today = fields.Date.context_today(self)
        for r in self:
            student, offering = r.student_id, r.offering_id
            if student.registration_state != 'registered' or student.programme_id != offering.programme_id:
                raise ValidationError('The student must be registered in the offering programme.')
            if offering.state != 'open' or not offering.semester_id.registration_start <= today <= offering.semester_id.registration_end:
                raise ValidationError('The course registration window is closed.')
            # Serialize approval for a class so concurrent approvals cannot exceed capacity.
            self.env.cr.execute('SELECT id FROM university_course_offering WHERE id = %s FOR UPDATE', (offering.id,))
            approved = self.sudo().search_count([('offering_id', '=', offering.id), ('state', '=', 'approved'), ('id', '!=', r.id)])
            if approved >= offering.capacity:
                raise ValidationError('This class has reached its approved capacity.')
            passed = self.env['student.result'].sudo().search([('student_id', '=', student.id), ('state', '=', 'published'), ('status', '=', 'pass')]).mapped('course_id')
            if offering.course_id.prerequisite_ids - passed:
                raise ValidationError('The student has not passed all prerequisite courses.')
            attempts = self.sudo().search_count([('student_id', '=', student.id), ('course_id', '=', r.course_id.id), ('state', '=', 'approved'), ('id', '!=', r.id)])
            if attempts >= r.policy_id.maximum_repeat_attempts:
                raise ValidationError('The approved repeat-attempt limit has been reached.')

    def action_submit(self):
        require_role(self.env, 'group_registrar', 'group_coordinator')
        if any(r.state != 'draft' for r in self):
            raise UserError('Only draft registrations can be submitted.')
        self._check_eligibility()
        return self._controlled_write({'state': 'submitted'}, 'Registration submitted')

    def action_approve(self):
        require_role(self.env, 'group_registrar', 'group_coordinator')
        if any(r.state != 'submitted' for r in self):
            raise UserError('Submit the course registration before approval.')
        self._check_eligibility()
        return self._controlled_write({'state': 'approved', 'approved_by': self.env.uid, 'approved_on': fields.Datetime.now()}, 'Course registration approved')

    def action_reject(self):
        require_role(self.env, 'group_registrar', 'group_coordinator')
        if any(r.state != 'submitted' or not r.reason for r in self):
            raise UserError('Reject a submitted registration with a recorded reason.')
        return self._controlled_write({'state': 'rejected'}, 'Registration rejected', self.mapped('reason'))

    def action_cancel(self):
        require_role(self.env, 'group_registrar')
        if any(r.state not in ('draft', 'submitted', 'approved') or not r.reason for r in self):
            raise UserError('Cancel an active registration with a recorded reason.')
        if any(r.result_ids or r.attendance_ids for r in self):
            raise UserError('Registrations with attendance or results must remain in the audit record.')
        return self._controlled_write({'state': 'cancelled'}, 'Registration cancelled')

    def action_reset(self):
        require_role(self.env, 'group_registrar', 'group_coordinator')
        if any(r.state not in ('rejected', 'cancelled') or not r.reason or r.attendance_ids or r.result_ids for r in self):
            raise UserError('Reopen a rejected/cancelled request with a reason and no attendance or results.')
        return self._controlled_write({'state': 'draft', 'approved_by': False, 'approved_on': False}, 'Registration reopened', self.mapped('reason'))

    def action_flag_absence(self):
        require_role(self.env, 'group_lecturer', 'group_coordinator', 'group_registrar')
        for r in self:
            if not r.absence_flag:
                raise UserError('This registration is not below the attendance threshold.')
            student = r.student_id.sudo()
            summary = 'Attendance review: %s' % r.offering_id.name
            existing = self.env['mail.activity'].sudo().search_count([('res_model', '=', 'student.university'), ('res_id', '=', student.id), ('summary', '=', summary)])
            if not existing:
                student.activity_schedule('mail.mail_activity_data_todo', user_id=r.coordinator_id.id, summary=summary,
                                          note='Attendance %.1f%%; required %.1f%%.' % (r.attendance_rate, r.policy_id.minimum_attendance))
            r._audit('Absence referred', summary)
        return True

    def action_prepare_result(self):
        require_role(self.env, 'group_lecturer', 'group_coordinator', 'group_registrar')
        self.ensure_one()
        self.check_access('read')
        if self.state != 'approved':
            raise UserError('Approve course registration before preparing an assessment.')
        result = self.result_ids or self.env['student.result'].create({'registration_id': self.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'student.result', 'res_id': result.id, 'view_mode': 'form'}


class ClassSession(models.Model):
    _name = 'university.class.session'
    _description = 'Timetabled Class Session'
    _inherit = ['university.academic.workflow']
    _order = 'start_datetime'

    name = fields.Char(required=True)
    offering_id = fields.Many2one('university.course.offering', required=True, ondelete='restrict')
    lecturer_id = fields.Many2one(related='offering_id.lecturer_id', store=True)
    coordinator_id = fields.Many2one(related='offering_id.coordinator_id', store=True)
    venue = fields.Char(required=True)
    start_datetime = fields.Datetime(required=True)
    end_datetime = fields.Datetime(required=True)
    state = fields.Selection([('draft', 'Draft'), ('published', 'Published'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='draft', required=True, copy=False)
    attendance_ids = fields.One2many('university.class.attendance', 'session_id')

    @api.constrains('start_datetime', 'end_datetime', 'offering_id')
    def _check_dates(self):
        for r in self:
            if r.end_datetime <= r.start_datetime:
                raise ValidationError('A session must end after it starts.')
            if not r.offering_id.semester_id.date_start <= r.start_datetime.date() <= r.end_datetime.date() <= r.offering_id.semester_id.date_end:
                raise ValidationError('Class times must be within the semester.')

    def write(self, vals):
        require_role(self.env, 'group_coordinator', 'group_registrar')
        if any(r.state != 'draft' for r in self):
            raise UserError('Published sessions are immutable. Cancel and create a replacement.')
        return super().write(vals)

    def action_publish(self):
        require_role(self.env, 'group_registrar', 'group_coordinator')
        for r in self:
            if r.state != 'draft':
                raise UserError('Only draft sessions can be published.')
            self.env.cr.execute('LOCK TABLE university_class_session IN SHARE ROW EXCLUSIVE MODE')
            conflicts = self.sudo().search([('id', '!=', r.id), ('state', 'in', ['published', 'completed']), ('start_datetime', '<', r.end_datetime), ('end_datetime', '>', r.start_datetime)])
            for other in conflicts:
                if other.lecturer_id == r.lecturer_id or other.venue.strip().casefold() == r.venue.strip().casefold() or other.offering_id.programme_id == r.offering_id.programme_id:
                    raise ValidationError('Timetable conflict: lecturer, venue or programme already has a session.')
            r._controlled_write({'state': 'published'}, 'Timetable published')
        return True

    def action_prepare_attendance(self):
        require_role(self.env, 'group_lecturer', 'group_coordinator', 'group_registrar')
        for r in self:
            if r.state != 'published':
                raise UserError('Prepare attendance for a published session.')
            registrations = r.offering_id.registration_ids.filtered(lambda reg: reg.state == 'approved')
            missing = registrations - r.attendance_ids.mapped('registration_id')
            self.env['university.class.attendance'].create([{'session_id': r.id, 'registration_id': reg.id} for reg in missing])
        return True

    def action_complete(self):
        require_role(self.env, 'group_lecturer', 'group_coordinator', 'group_registrar')
        for r in self:
            r.action_prepare_attendance()
            if r.end_datetime > fields.Datetime.now():
                raise UserError('Complete attendance only after the class has ended.')
            if not r.attendance_ids or any(a.status == 'unmarked' for a in r.attendance_ids):
                raise UserError('Mark every registered student before completing attendance.')
            r._controlled_write({'state': 'completed'}, 'Attendance finalized')
        return True

    def action_cancel(self):
        require_role(self.env, 'group_coordinator', 'group_registrar')
        if any(r.state == 'completed' for r in self):
            raise UserError('Completed classes cannot be cancelled.')
        return self._controlled_write({'state': 'cancelled'}, 'Session cancelled')


class ClassAttendance(models.Model):
    _name = 'university.class.attendance'
    _description = 'Student Class Attendance'
    _inherit = ['university.academic.workflow']
    _rec_name = 'registration_id'

    session_id = fields.Many2one('university.class.session', required=True, ondelete='restrict')
    registration_id = fields.Many2one('university.course.registration', required=True, ondelete='restrict')
    student_id = fields.Many2one(related='registration_id.student_id', store=True)
    lecturer_id = fields.Many2one(related='session_id.lecturer_id', store=True)
    coordinator_id = fields.Many2one(related='session_id.coordinator_id', store=True)
    status = fields.Selection([('unmarked', 'Unmarked'), ('present', 'Present'), ('late', 'Late'), ('absent', 'Absent'), ('excused', 'Excused')], default='unmarked', required=True)
    correction_reason = fields.Text()

    _sql_constraints = [('unique_attendance', 'unique(session_id,registration_id)', 'Attendance already exists for this student and session.')]

    @api.constrains('session_id', 'registration_id')
    def _check_registration(self):
        for r in self:
            if r.registration_id.state != 'approved' or r.registration_id.offering_id != r.session_id.offering_id:
                raise ValidationError('Attendance requires an approved registration in this class.')

    @api.model_create_multi
    def create(self, vals_list):
        sessions = self.env['university.class.session'].browse([v['session_id'] for v in vals_list])
        if any(s.state != 'published' for s in sessions):
            raise UserError('Attendance may only be created for published sessions.')
        return super().create(vals_list)

    def write(self, vals):
        if {'registration_id', 'session_id'} & set(vals):
            raise UserError('Attendance records cannot be reassigned.')
        if any(r.session_id.state == 'cancelled' for r in self):
            raise UserError('A cancelled class cannot be marked.')
        for r in self:
            if r.session_id.state == 'completed':
                require_role(self.env, 'group_coordinator', 'group_registrar')
                reason = vals.get('correction_reason', '').strip()
                if 'status' in vals and (not reason or reason == (r.correction_reason or '').strip()):
                    raise ValidationError('Record a new reason for each attendance correction.')
                if 'status' in vals:
                    r._audit('Attendance corrected', '%s -> %s; %s' % (r.status, vals['status'], reason))
        return super().write(vals)

    def unlink(self):
        if any(r.session_id.state == 'completed' for r in self):
            raise UserError('Final attendance cannot be deleted.')
        return super().unlink()


class AcademicAppeal(models.Model):
    _name = 'university.academic.appeal'
    _description = 'Student Academic Appeal'
    _inherit = ['university.academic.workflow']
    _rec_name = 'result_id'

    result_id = fields.Many2one('student.result', required=True, ondelete='restrict')
    student_id = fields.Many2one(related='result_id.student_id', store=True)
    coordinator_id = fields.Many2one(related='result_id.registration_id.coordinator_id', store=True)
    reason = fields.Text(required=True)
    resolution = fields.Text()
    state = fields.Selection([('draft', 'Submitted'), ('resolved', 'Resolved'), ('rejected', 'Rejected')], default='draft', required=True, copy=False)
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)

    @api.constrains('result_id')
    def _check_result(self):
        for r in self:
            if r.result_id.state != 'published':
                raise ValidationError('Appeals can only concern published results.')
            deadline = fields.Datetime.to_datetime(r.result_id.published_on) + timedelta(days=r.result_id.policy_id.appeal_days)
            if fields.Datetime.now() > deadline:
                raise ValidationError('The appeal submission window has closed.')

    def write(self, vals):
        if any(r.state != 'draft' for r in self) or set(vals) - {'resolution'}:
            raise UserError('Only the resolution can be edited while an appeal is open.')
        return super().write(vals)

    def action_resolve(self):
        require_role(self.env, 'group_exam_board', 'group_registrar')
        if any(r.state != 'draft' or not r.resolution for r in self):
            raise UserError('Record a resolution for the open appeal.')
        return self._controlled_write({'state': 'resolved', 'approved_by': self.env.uid, 'approved_on': fields.Datetime.now()}, 'Appeal resolved', self.mapped('resolution'))

    def action_reject(self):
        require_role(self.env, 'group_exam_board', 'group_registrar')
        if any(r.state != 'draft' or not r.resolution for r in self):
            raise UserError('Record a rejection reason for the open appeal.')
        return self._controlled_write({'state': 'rejected', 'approved_by': self.env.uid, 'approved_on': fields.Datetime.now()}, 'Appeal rejected', self.mapped('resolution'))
