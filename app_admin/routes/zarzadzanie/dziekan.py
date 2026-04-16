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

# ── Dziekan ───────────────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/dziekan')
@wymaga_roli(UserRole.ADMIN)
def dziekan_lista():
    strona    = request.args.get('page', 1, type=int)
    wnioski   = _repo_zapisow.wnioski_dziekana_strona(strona=strona)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/dziekan/lista.html', wnioski=wnioski, csrf_form=csrf_form)


@zarzadzanie_bp.route('/dziekan/<uuid:id>/decyzja', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def dziekan_decyzja(id):
    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SelectField, SubmitField
    from wtforms.validators import DataRequired, Optional

    zapis = db.session.get(InternshipEnrollment, id) or abort(404)

    if zapis.status != EnrollmentStatus.DEAN_APPROVAL:
        flash('Wniosek nie wymaga decyzji dziekana.', 'warning')
        return redirect(url_for('zarzadzanie.dziekan_lista'))

    class FormularzDziekana(FlaskForm):
        decyzja   = SelectField('Decyzja dziekana', choices=[
            ('APPROVED', 'Wyrażam zgodę na zaliczenie praktyki'),
            ('REJECTED', 'Nie wyrażam zgody na zaliczenie'),
        ], validators=[DataRequired()])
        komentarz = TextAreaField('Komentarz dziekana', validators=[Optional()])
        submit    = SubmitField('Zapisz decyzję')

    form = FormularzDziekana()

    if form.validate_on_submit():
        from core.uslugi.workflow import ZapisFSM, IllegalTransitionError

        try:
            with ZapisFSM.lock(id) as fsm:
                if fsm.zapis.status != EnrollmentStatus.DEAN_APPROVAL:
                    flash('Wniosek zmienił status podczas przetwarzania — spróbuj ponownie.', 'warning')
                    return redirect(url_for('zarzadzanie.dziekan_lista'))

                komentarz = form.komentarz.data or ''
                if form.decyzja.data == 'APPROVED':
                    fsm.zatwierdz_przez_dziekana(actor_id=current_user.id, comment=komentarz)
                    flash('Wniosek zatwierdzony przez dziekana. Student może kontynuować praktykę.', 'success')
                else:
                    from core.modele.praktyki import EventType
                    fsm.odrzuc(actor_id=current_user.id,
                               comment=f"Dziekan nie wyraził zgody: {komentarz}",
                               event_type=EventType.DEAN_DECISION)
                    flash('Wniosek odrzucony przez dziekana.', 'warning')

                db.session.commit()
        except IllegalTransitionError as e:
            flash(str(e), 'danger')
        return redirect(url_for('zarzadzanie.dziekan_lista'))

    return render_template('zarzadzanie/dziekan/decyzja.html', form=form, zapis=zapis)


