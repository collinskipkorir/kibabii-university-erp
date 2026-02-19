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
