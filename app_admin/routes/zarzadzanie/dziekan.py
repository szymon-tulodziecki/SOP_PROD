import uuid
import csv
import io
import datetime
from datetime import timezone as _tz
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError
from werkzeug.security import generate_password_hash

from core.modele import (User, Student, Internship, InternshipEnrollment, InternshipSchedule, LearningOutcome,
                    UserRole, InternshipStatus, EnrollmentStatus, UploadedDocument, Company)
from core.extensions import db
from core.uslugi import UslugaUzytkownikow as _UslugaUzytkownikow
_serwis_uzytkownikow = _UslugaUzytkownikow()
from core.autoryzacja import wymaga_roli
from core.repozytoria import RepozytoriumZapisow

_repo_zapisow = RepozytoriumZapisow()

from . import zarzadzanie_bp
from .formularze import *

# ── Dyrektor Instytutu ────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/dziekan')
@wymaga_roli(UserRole.ADMIN, UserRole.DYREKTOR)
def dziekan_lista():
    strona    = request.args.get('page', 1, type=int)
    wnioski   = _repo_zapisow.wnioski_dziekana_strona(strona=strona)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/dziekan/lista.html', wnioski=wnioski, csrf_form=csrf_form)


@zarzadzanie_bp.route('/dziekan/<uuid:id>/decyzja', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.DYREKTOR)
def dziekan_decyzja(id):
    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SelectField, SubmitField
    from wtforms.validators import DataRequired, Optional

    zapis = db.session.get(InternshipEnrollment, id) or abort(404)

    if zapis.status != EnrollmentStatus.DIRECTOR_APPROVAL:
        flash('Wniosek nie wymaga decyzji Dyrektora Instytutu.', 'warning')
        return redirect(url_for('zarzadzanie.dziekan_lista'))

    class FormularzDyrektora(FlaskForm):
        decyzja   = SelectField('Decyzja Dyrektora Instytutu', choices=[
            ('APPROVED', 'Wyrażam zgodę na zaliczenie praktyki'),
            ('REJECTED', 'Nie wyrażam zgody na zaliczenie'),
        ], validators=[DataRequired()])
        komentarz = TextAreaField('Komentarz dyrektora', validators=[Optional()])
        submit    = SubmitField('Zapisz decyzję')

    form = FormularzDyrektora()

    if form.validate_on_submit():
        from core.uslugi.workflow import ZapisFSM, IllegalTransitionError

        try:
            with ZapisFSM.lock(id) as fsm:
                if fsm.zapis.status != EnrollmentStatus.DIRECTOR_APPROVAL:
                    flash('Wniosek zmienił status podczas przetwarzania — spróbuj ponownie.', 'warning')
                    return redirect(url_for('zarzadzanie.dziekan_lista'))

                komentarz = form.komentarz.data or ''
                if form.decyzja.data == 'APPROVED':
                    fsm.zatwierdz_przez_dyrektora(actor_id=current_user.id, comment=komentarz)
                    flash('Wniosek zatwierdzony przez Dyrektora Instytutu. Student może kontynuować praktykę.', 'success')
                else:
                    from core.modele.praktyki import EventType
                    fsm.odrzuc(actor_id=current_user.id,
                               comment=f"Dyrektor nie wyraził zgody: {komentarz}",
                               event_type=EventType.DIRECTOR_DECISION)
                    flash('Wniosek odrzucony przez Dyrektora Instytutu.', 'warning')

                db.session.commit()
        except IllegalTransitionError as e:
            flash(str(e), 'danger')
        return redirect(url_for('zarzadzanie.dziekan_lista'))

    dokumenty = (
        db.session.query(UploadedDocument)
        .filter_by(enrollment_id=id, is_deleted=False)
        .order_by(UploadedDocument.uploaded_at.desc())
        .all()
    )
    return render_template('zarzadzanie/dziekan/decyzja.html', form=form, zapis=zapis, dokumenty=dokumenty)
