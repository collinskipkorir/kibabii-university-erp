from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UniversityManagement(models.Model):
    _name = 'university.management'
    _description = 'University Management'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    # =========================
    # Basic Information
    # =========================
    name = fields.Char(
        string='University Name',
        required=True,
        tracking=True
    )

    code = fields.Char(
        string='University Code',
        readonly=True,
        copy=False,
        default='New'
    )

    location = fields.Char(string='University Location')
    email = fields.Char(string='University Email')
    phone_number = fields.Char(string='University Phone Number')

    # =========================
    # Admission Control
    # =========================
    admission_slots_needed = fields.Integer(string="Admission Slots Needed")
    admission_slots_remaining = fields.Integer(string="Admission Slots Remaining")

    # =========================
    # Relations
    # =========================
    student_ids = fields.One2many(
        'student.university',
        'university_id',
        string="Students"
    )



    department_ids = fields.One2many(
        'university.department',
        'university_id',
        string="Departments"
    )

    course_ids = fields.One2many(
        'university.course',
        'university_id',
        string="Courses"
    )

    fee_ids = fields.One2many(
        'university.fee',
        'university_id',
        string="Fees"
    )

    result_ids = fields.One2many(
        'student.result',
        'university_id',
        string="Results"
    )

    # =========================
    # Computed Statistics
    # =========================
    total_students = fields.Integer(
        string="Total Students",
        compute='_compute_statistics',
        store=True
    )

    total_courses = fields.Integer(
        string="Total Courses",
        compute='_compute_statistics',
        store=True
    )

    total_departments = fields.Integer(
        string="Total Departments",
        compute='_compute_statistics',
        store=True
    )

    @api.depends('student_ids', 'course_ids', 'department_ids')
    def _compute_statistics(self):
        for record in self:
            record.total_students = len(record.student_ids)
            record.total_courses = len(record.course_ids)
            record.total_departments = len(record.department_ids)

    # =========================
    # Constraints
    # =========================
    @api.constrains('admission_slots_remaining', 'admission_slots_needed')
    def _check_admission_slots(self):
        for record in self:
            if record.admission_slots_remaining < 0:
                raise ValidationError("Remaining slots cannot be negative.")

            if record.admission_slots_remaining < record.admission_slots_needed:
                raise ValidationError(
                    "Remaining slots cannot be less than needed slots."
                )

    # =========================
    # Sequence Generation
    # =========================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'university.management'
                ) or 'New'
        return super().create(vals_list)

    # =========================
    # Delete Protection
    # =========================
    def unlink(self):
        for record in self:
            if record.student_ids:
                raise ValidationError(
                    "You cannot delete a university that has students."
                )
        return super().unlink()