from odoo import api, fields, models
from odoo.exceptions import ValidationError


class StudentResults(models.Model):
    _name = 'student.result'
    _description = 'Student Result'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'student_id'

    # =========================
    # Relations
    # =========================
    student_id = fields.Many2one(
        'student.university',
        string="Student",
        required=True,
        ondelete='cascade',
        tracking=True
    )

    course_id = fields.Many2one(
        'university.course',
        string="Course",
        required=True,
        ondelete='cascade',
        tracking=True
    )

    # =========================
    # Academic Fields
    # =========================
    marks = fields.Float(
        string="Marks (%)",
        required=True,
        tracking=True
    )

    credit_units = fields.Integer(
        string="Credit Units",
        required=True
    )

    university_id = fields.Many2one(
        'university.management',
        string='University Management',
        ondelete='cascade'
    )

    grade = fields.Char(
        string="Grade",
        compute="_compute_grade",
        store=True
    )

    grade_point = fields.Float(
        string="Grade Point",
        compute="_compute_grade",
        store=True
    )

    status = fields.Selection(
        [
            ('pass', 'Pass'),
            ('fail', 'Fail')
        ],
        compute="_compute_grade",
        store=True,
        string="Status"
    )

    # =========================
    # Grade Computation Logic
    # =========================
    @api.depends('marks')
    def _compute_grade(self):
        for rec in self:
            if rec.marks >= 70:
                rec.grade = 'A'
                rec.grade_point = 4.0
                rec.status = 'pass'
            elif rec.marks >= 60:
                rec.grade = 'B'
                rec.grade_point = 3.0
                rec.status = 'pass'
            elif rec.marks >= 50:
                rec.grade = 'C'
                rec.grade_point = 2.0
                rec.status = 'pass'
            elif rec.marks >= 40:
                rec.grade = 'D'
                rec.grade_point = 1.0
                rec.status = 'pass'
            else:
                rec.grade = 'F'
                rec.grade_point = 0.0
                rec.status = 'fail'

    # =========================
    # Constraints
    # =========================
    @api.constrains('marks')
    def _check_marks(self):
        for rec in self:
            if rec.marks < 0 or rec.marks > 100:
                raise ValidationError("Marks must be between 0 and 100.")

    @api.constrains('credit_units')
    def _check_credit_units(self):
        for rec in self:
            if rec.credit_units <= 0:
                raise ValidationError("Credit units must be greater than zero.")