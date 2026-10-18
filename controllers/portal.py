from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError
from werkzeug.exceptions import NotFound


class UniversityWebsite(http.Controller):
    @http.route('/universities', type='http', auth='public', website=True)
    def universities(self, **kw):
        universities = request.env['university.management'].sudo().search([])
        return request.render('kibabii-university-erp.university_list_template', {'universities': universities})


class StudentPortal(http.Controller):
    def _student(self):
        if not request.env.user.has_group('kibabii-university-erp.group_student'):
            raise NotFound()
        return request.env['student.university'].search([('user_id', '=', request.env.user.id)], limit=1)

    @http.route(['/my/student', '/my/student/dashboard'], type='http', auth='user', website=True)
    def student_dashboard(self, **kw):
        return request.render('kibabii-university-erp.student_dashboard_template', {'student': self._student()})

    @http.route('/student/register', type='http', auth='public', website=True)
    def student_register(self, **kw):
        return request.render('kibabii-university-erp.student_registration', {
            'universities': request.env['university.management'].sudo().search([]), 'error': False,
        })

    @http.route('/student/register/submit', type='http', auth='public', methods=['POST'], website=True)
    def student_register_submit(self, **post):
        universities = request.env['university.management'].sudo().search([])
        try:
            with request.env.cr.savepoint():
                name = (post.get('name') or '').strip()
                email = (post.get('email') or '').strip().lower()
                phone = (post.get('phone_number') or '').strip()
                password = post.get('password') or ''
                university_id = int(post.get('university_id') or 0)
                if not name or '@' not in email or not phone or not password or university_id not in universities.ids:
                    raise ValidationError('Enter your name, email, phone, password and a valid university.')
                if request.env['res.users'].sudo().with_context(active_test=False).search_count([('login', '=', email)]):
                    raise ValidationError('This email is already registered. Please sign in or reset your password.')
                user = request.env['res.users'].sudo().with_context(no_reset_password=True).create({
                    'name': name, 'login': email, 'email': email, 'password': password,
                    'groups_id': [(6, 0, [request.env.ref('kibabii-university-erp.group_student').id])],
                })
                request.env['student.university'].sudo().create({
                    'name': name, 'email': email, 'phone_number': phone,
                    'university_id': university_id, 'user_id': user.id,
                })
        except (ValidationError, ValueError) as error:
            return request.render('kibabii-university-erp.student_registration', {
                'universities': universities, 'error': str(error),
            })
        return request.redirect('/web/login')

    @http.route('/my/results', type='http', auth='user', website=True)
    def student_results(self, **kw):
        student = self._student()
        results = request.env['student.result'].search([('student_id', '=', student.id), ('state', '=', 'published')])
        return request.render('kibabii-university-erp.student_results', {'results': results})

    @http.route('/my/transcript/<int:student_id>', type='http', auth='user')
    def download_transcript(self, student_id, **kw):
        student = self._student()
        if not student or student.id != student_id:
            raise NotFound()
        pdf, _ = request.env['ir.actions.report']._render_qweb_pdf(
            'kibabii-university-erp.student_transcript_report', res_ids=student.ids
        )
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', 'attachment; filename=transcript.pdf'),
        ])

    @http.route('/my/fees', type='http', auth='user', website=True)
    def student_fees(self, **kw):
        student = self._student()
        fees = request.env['university.fee'].search([('student_id', '=', student.id)])
        return request.render('kibabii-university-erp.student_fees', {'fees': fees})
