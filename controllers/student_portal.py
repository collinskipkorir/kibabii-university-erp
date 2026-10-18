import base64

from odoo import http, fields
from odoo.http import request
from odoo.exceptions import UserError, ValidationError
from werkzeug.exceptions import NotFound
from werkzeug.utils import secure_filename

from .portal import StudentPortal

MODULE = 'kibabii-university-erp'


class AcademicStudentPortal(StudentPortal):
    def _profile_values(self, student, error=False):
        return {
            'student': student.sudo(), 'error': error,
            'programmes': request.env['university.programme'].sudo().search([('university_id', '=', student.university_id.id)]),
            'years': request.env['university.academic.year'].sudo().search([]),
            'countries': request.env['res.country'].sudo().search([]),
        }

    @http.route('/my/student/profile', type='http', auth='user', website=True)
    def student_profile(self, **kw):
        student = self._student()
        if not student:
            raise NotFound()
        return request.render(MODULE + '.academic_student_profile', self._profile_values(student))

    @http.route('/my/student/profile/save', type='http', auth='user', website=True, methods=['POST'])
    def student_profile_save(self, **post):
        student = self._student()
        if not student:
            raise NotFound()
        try:
            with request.env.cr.savepoint():
                contact_fields = ['phone_number', 'street', 'street2', 'city', 'postal_code', 'guardian_name', 'guardian_relationship', 'guardian_phone', 'guardian_email', 'emergency_name', 'emergency_relationship', 'emergency_phone', 'sponsor_name', 'sponsor_contact']
                draft_fields = ['name', 'date_of_birth', 'identity_number', 'intake', 'previous_school', 'entry_qualification']
                allowed = contact_fields + (draft_fields if student.registration_state == 'applicant' else [])
                vals = {name: (post[name].strip() or False) for name in allowed if name in post}
                if student.registration_state == 'applicant':
                    for name, model in [('nationality_id', 'res.country'), ('country_id', 'res.country'), ('academic_year_id', 'university.academic.year'), ('programme_id', 'university.programme')]:
                        if name in post:
                            record = request.env[model].sudo().browse(int(post[name] or 0)).exists()
                            if not record:
                                raise ValidationError('Select a valid country, academic year and programme.')
                            if name == 'programme_id' and record.university_id != student.university_id:
                                raise ValidationError('Select a programme at your university.')
                            vals[name] = record.id
                    if 'study_mode' in post:
                        vals['study_mode'] = post['study_mode']
                    if 'gender' in post and post['gender']:
                        vals['gender'] = post['gender']
                    if post.get('identity_type'):
                        vals['identity_type'] = post['identity_type']
                student.sudo().write(vals)
                if post.get('submit_application'):
                    student.sudo().action_submit_application()
        except (UserError, ValueError) as error:
            return request.render(MODULE + '.academic_student_profile', self._profile_values(student, str(error)))
        return request.redirect('/my/student/profile')

    @http.route('/my/student/document', type='http', auth='user', website=True, methods=['POST'])
    def student_document_upload(self, **post):
        student = self._student()
        if not student or student.registration_state != 'applicant':
            raise NotFound()
        try:
            with request.env.cr.savepoint():
                upload = request.httprequest.files.get('document')
                data = upload.read(10 * 1024 * 1024 + 1) if upload else b''
                if not data or len(data) > 10 * 1024 * 1024 or not data.startswith((b'%PDF-', b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n')):
                    raise ValidationError('Upload a PDF, JPEG or PNG document no larger than 10 MB.')
                kind = post.get('kind')
                if kind not in ('identity', 'qualification', 'photo', 'other'):
                    raise ValidationError('Select a valid document type.')
                filename = secure_filename(upload.filename) or 'document'
                request.env['university.student.document'].sudo().create({
                    'student_id': student.id, 'name': filename, 'filename': filename,
                    'kind': kind, 'file_data': base64.b64encode(data),
                })
        except UserError as error:
            return request.render(MODULE + '.academic_student_profile', self._profile_values(student, str(error)))
        return request.redirect('/my/student/profile')

    @http.route('/my/student/courses', type='http', auth='user', website=True)
    def student_courses(self, **kw):
        student = self._student()
        if not student:
            raise NotFound()
        today = fields.Date.context_today(student)
        offerings = request.env['university.course.offering'].sudo().search([
            ('programme_id', '=', student.programme_id.id), ('state', '=', 'open'),
            ('semester_id.registration_start', '<=', today), ('semester_id.registration_end', '>=', today),
        ]) if student.registration_state == 'registered' else request.env['university.course.offering']
        return request.render(MODULE + '.academic_student_courses', {'student': student, 'offerings': offerings, 'error': kw.get('error')})

    @http.route('/my/student/courses/register', type='http', auth='user', website=True, methods=['POST'])
    def student_course_register(self, **post):
        student = self._student()
        if not student:
            raise NotFound()
        try:
            with request.env.cr.savepoint():
                offering = request.env['university.course.offering'].sudo().browse(int(post.get('offering_id') or 0)).exists()
                if not offering or offering.programme_id != student.programme_id:
                    raise ValidationError('Select a class in your programme.')
                self.env_lock_student(student)
                existing = request.env['university.course.registration'].sudo().search([('student_id', '=', student.id), ('offering_id', '=', offering.id)])
                if existing:
                    raise ValidationError('A registration request already exists for this class.')
                registration = request.env['university.course.registration'].sudo().create({'student_id': student.id, 'offering_id': offering.id})
                registration.action_submit()
        except (UserError, ValueError) as error:
            from urllib.parse import urlencode
            return request.redirect('/my/student/courses?' + urlencode({'error': str(error)}))
        return request.redirect('/my/student/courses')

    def env_lock_student(self, student):
        request.env.cr.execute('SELECT id FROM student_university WHERE id=%s FOR UPDATE', (student.id,))

    @http.route('/my/student/timetable', type='http', auth='user', website=True)
    def student_timetable(self, **kw):
        student = self._student()
        if not student:
            raise NotFound()
        sessions = request.env['university.class.session'].search([
            ('offering_id', 'in', student.registration_ids.filtered(lambda r: r.state == 'approved').offering_id.ids),
            ('state', 'in', ['published', 'completed']),
        ])
        return request.render(MODULE + '.academic_student_timetable', {'sessions': sessions, 'student': student})

    @http.route('/my/student/attendance', type='http', auth='user', website=True)
    def student_attendance(self, **kw):
        student = self._student()
        if not student:
            raise NotFound()
        return request.render(MODULE + '.academic_student_attendance', {'student': student, 'registrations': student.registration_ids.filtered(lambda r: r.state == 'approved')})

    @http.route('/my/student/appeals', type='http', auth='user', website=True)
    def student_appeals(self, **kw):
        student = self._student()
        if not student:
            raise NotFound()
        return request.render(MODULE + '.academic_student_appeals', {
            'student': student, 'results': student.published_result_ids,
            'appeals': request.env['university.academic.appeal'].search([('student_id', '=', student.id)]),
            'error': kw.get('error'),
        })

    @http.route('/my/student/appeals/submit', type='http', auth='user', website=True, methods=['POST'])
    def student_appeal_submit(self, **post):
        student = self._student()
        try:
            with request.env.cr.savepoint():
                result = request.env['student.result'].search([('id', '=', int(post.get('result_id') or 0)), ('student_id', '=', student.id), ('state', '=', 'published')])
                reason = (post.get('reason') or '').strip()
                if not result or not reason:
                    raise ValidationError('Select your published result and provide an appeal reason.')
                self.env_lock_student(student)
                if request.env['university.academic.appeal'].sudo().search_count([('result_id', '=', result.id), ('state', '=', 'draft')]):
                    raise ValidationError('An appeal for this result is already under review.')
                request.env['university.academic.appeal'].sudo().create({'result_id': result.id, 'reason': reason})
        except (UserError, ValueError) as error:
            from urllib.parse import urlencode
            return request.redirect('/my/student/appeals?' + urlencode({'error': str(error)}))
        return request.redirect('/my/student/appeals')
