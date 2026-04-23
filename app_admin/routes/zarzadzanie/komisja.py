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
from core.repozytoria import RepozytoriumZapisow, RepozytoriumDokumentowStudenta

_repo_zapisow = RepozytoriumZapisow()
_repo_docs    = RepozytoriumDokumentowStudenta()

from . import zarzadzanie_bp
from .formularze import *

# ── Komisja weryfikująca ──────────────────────────────────────────────────────

@zarzadzanie_bp.route('/komisja')
@wymaga_roli(UserRole.ADMIN, UserRole.KOMISJA)
def komisja_lista():
    strona    = request.args.get('page', 1, type=int)
    wnioski   = _repo_zapisow.wnioski_komisja_strona(strona=strona)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/komisja/lista.html', wnioski=wnioski, csrf_form=csrf_form)


@zarzadzanie_bp.route('/komisja/<uuid:id>/weryfikuj', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.KOMISJA)
def komisja_weryfikuj(id):
    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SelectField, SubmitField
    from wtforms.validators import DataRequired, Optional

    zapis = db.session.get(InternshipEnrollment, id) or abort(404)

    if zapis.status not in (EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.REVISION_REQUIRED):
        flash('Wniosek nie wymaga weryfikacji komisji.', 'warning')
        return redirect(url_for('zarzadzanie.komisja_lista'))

    class FormularzKomisji(FlaskForm):
        decyzja   = SelectField('Decyzja komisji', choices=[
            ('APPROVED',           'Zatwierdzam - kieruję do Dyrektora Instytutu'),
            ('PARTIALLY_APPROVED', 'Zatwierdzam częściowo - wymaga uzupełnień'),
            ('REJECTED',           'Odrzucam wniosek'),
        ], validators=[DataRequired()])
        komentarz = TextAreaField('Komentarz komisji', validators=[Optional()])
        submit    = SubmitField('Zapisz decyzję')

    form = FormularzKomisji()

    if form.validate_on_submit():
        from core.uslugi.workflow import ZapisFSM, IllegalTransitionError

        try:
            with ZapisFSM.lock(id) as fsm:
                if fsm.zapis.status not in (EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.REVISION_REQUIRED):
                    flash('Wniosek zmienił status podczas przetwarzania — spróbuj ponownie.', 'warning')
                    return redirect(url_for('zarzadzanie.komisja_lista'))

                komentarz = form.komentarz.data or ''
                if form.decyzja.data == 'APPROVED':
                    fsm.zatwierdz_przez_komisje(actor_id=current_user.id, comment=komentarz)
                    flash('Wniosek zatwierdzony i przekazany do Dyrektora Instytutu.', 'success')
                elif form.decyzja.data == 'PARTIALLY_APPROVED':
                    fsm.zadaj_poprawki(actor_id=current_user.id, comment=komentarz)
                    flash('Wniosek wymaga uzupełnień - student zostanie powiadomiony.', 'info')
                else:
                    from core.modele.praktyki import EventType
                    fsm.odrzuc(actor_id=current_user.id,
                               comment=f"Wniosek odrzucony przez komisję: {komentarz}",
                               event_type=EventType.COMMITTEE_DECISION)
                    flash('Wniosek został odrzucony.', 'warning')

                db.session.commit()
        except IllegalTransitionError as e:
            flash(str(e), 'danger')
        return redirect(url_for('zarzadzanie.komisja_lista'))

    dokumenty = _repo_docs.dla_zapisu_studenta(id, zapis.student_id)
    return render_template('zarzadzanie/komisja/weryfikuj.html',
                           form=form, zapis=zapis, dokumenty=dokumenty)


