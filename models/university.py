from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UniversityManagement(models.Model):
    _name = 'university.management'
    _description = 'University Management'


    name = fields.Char(string='University Name')
    location = fields.Char(string='University Location')
    email = fields.Char(string='University Email')
    phone_number = fields.Char(string='University Phone Number')
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


    @api.constrains('admission_slots_remaining' , 'admission_slots_needed')
    def _check_admission_slots(self):
        for record in self:
            if record.admission_slots_remaining < record.admission_slots_needed:
                raise ValidationError('not enough admission slots')


    @api.model_create_multi
    def create(self, vals):
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'university.course'
                )
            return super().create(vals)


    @api.onchange('student_ids')
    def onchange_student_ids(self):
        if self.student_ids:
            self.student_ids = self.student_ids.filtered()




