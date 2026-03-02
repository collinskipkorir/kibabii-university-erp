from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UniversityCourse(models.Model):
    _name = 'university.course'
    _description = 'University Course'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(
        string="Course Name",
        required=True,
        tracking=True
    )

    code = fields.Char(
        string="Course Code",
        readonly=True,
        copy=False,
        default="New",
        tracking=True
    )

    description = fields.Text(string="Course Description")

    credit_units = fields.Integer(
        string="Credit Units",
        required=True
    )

    active = fields.Boolean(default=True)

    # =========================
    # Relations
    # =========================
    university_id = fields.Many2one(
        'university.management',
        string="University",
        required=True,
        ondelete='cascade'
    )

    department_id = fields.Many2one(
        'university.department',
        string="Department",
        ondelete='set null'
    )

    student_ids = fields.One2many(
        'student.university',
        'course_id',
        string="Students"
    )

    result_ids = fields.One2many(
        'student.result',
        'course_id',
        string="Results"
    )

    # =========================
    # Computed Fields
    # =========================
    total_students = fields.Integer(
        string="Total Students",
        compute='_compute_total_students',
        store=True
    )

    @api.depends('student_ids')
    def _compute_total_students(self):
        for course in self:
            course.total_students = len(course.student_ids)

    # =========================
    # Constraints
    # =========================
    @api.constrains('credit_units')
    def _check_credit_units(self):
        for record in self:
            if record.credit_units <= 0:
                raise ValidationError("Credit units must be greater than zero.")

    # =========================
    # Sequence Generation
    # =========================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'university.course'
                ) or 'New'
        return super().create(vals_list)

    # =========================
    # Delete Protection
    # =========================
    def unlink(self):
        for record in self:
            if record.student_ids:
                raise ValidationError(
                    "You cannot delete a course that has enrolled students."
                )
        return super().unlink()