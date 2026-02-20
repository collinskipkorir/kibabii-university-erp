from odoo import api, fields, models


class UniversityStudent(models.Model):
    _name = 'student.university'
    _description = 'University Student'

    #fields
    name = fields.Char(required=True , string="Student Name")
    email = fields.Char(required=True , string="Student Email")
    phone_number = fields.Char(required=True , string="Student Phone Number")
    date_of_admission = fields.Date(string="Date of Admission")
    registration_number = fields.Char(string="Registration Number")
    university_id = fields.Many2one(
        'university.management',
        string="University",
        ondelete='cascade',
        required=True
    )
    fee_ids = fields.One2many('university.fee', 'student_id')

    total_fee = fields.Float(compute='_compute_fee')
    total_paid = fields.Float(compute='_compute_fee')
    fee_balance = fields.Float(compute='_compute_fee')

    @api.depends('fee_ids.amount', 'fee_ids.paid_amount')
    def _compute_fee(self):
        for student in self:
            total = sum(f.amount for f in student.fee_ids)
            paid = sum(f.paid_amount for f in student.fee_ids)

            student.total_fee = total
            student.total_paid = paid
            student.fee_balance = total - paid

    course_id = fields.Many2one('university.course')
    result_ids = fields.One2many('student.result', 'student_id')

    total_credits = fields.Float(compute='_compute_gpa')
    total_points = fields.Float(compute='_compute_gpa')
    gpa = fields.Float(compute='_compute_gpa', store=True)

    @api.depends('result_ids.marks', 'result_ids.credit_units')
    def _compute_gpa(self):
        for student in self:
            total_points = 0.0
            total_credits = 0.0

            for result in student.result_ids:
                grade_point = 0

                if result.marks >= 70:
                    grade_point = 4
                elif result.marks >= 60:
                    grade_point = 3
                elif result.marks >= 50:
                    grade_point = 2
                elif result.marks >= 40:
                    grade_point = 1
                else:
                    grade_point = 0

                total_points += grade_point * result.credit_units
                total_credits += result.credit_units

            student.total_points = total_points
            student.total_credits = total_credits
            student.gpa = total_points / total_credits if total_credits else 0