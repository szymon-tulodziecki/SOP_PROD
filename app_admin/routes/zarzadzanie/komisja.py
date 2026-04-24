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
    from wtforms import TextAreaField
    from wtforms.validators import Optional
    from core.modele import CommitteeOutcomeEvaluation, AssessmentResult

    zapis = db.session.get(InternshipEnrollment, id) or abort(404)

    if zapis.status not in (EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.REVISION_REQUIRED):
        flash('Wniosek nie wymaga weryfikacji komisji.', 'warning')
        return redirect(url_for('zarzadzanie.komisja_lista'))

    class FormularzKomisji(FlaskForm):
        komentarz = TextAreaField('Komentarz ogólny komisji', validators=[Optional()])

    form = FormularzKomisji()
    efekty = LearningOutcome.query.order_by(LearningOutcome.id).all()

    ACTIVE_STATUSES = (EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.AWAITING_APPROVAL)

    if form.validate_on_submit():
        if zapis.status not in ACTIVE_STATUSES:
            flash('Wniosek nie jest w stanie umożliwiającym decyzję komisji.', 'warning')
            return redirect(url_for('zarzadzanie.komisja_lista'))

        opinia = request.form.get('opinia')
        if opinia not in ('APPROVED', 'PARTIALLY_APPROVED', 'REJECTED'):
            flash('Wybierz opinię komisji (jeden z trzech przycisków).', 'warning')
            istniejace = {e.learning_outcome_id: e for e in CommitteeOutcomeEvaluation.query.filter_by(enrollment_id=id).all()}
            dokumenty  = _repo_docs.dla_zapisu_studenta(id, zapis.student_id)
            return render_template('zarzadzanie/komisja/weryfikuj.html',
                                   form=form, zapis=zapis, dokumenty=dokumenty,
                                   efekty=efekty, istniejace=istniejace)

        errors     = []
        evaluations = []
        for efekt in efekty:
            wynik_val = request.form.get(f'outcome_{efekt.id}')
            if not wynik_val:
                errors.append(f'Efekt {efekt.kod}: brak oceny')
                continue
            notes_val = request.form.get(f'notes_{efekt.id}', '').strip()
            if wynik_val == 'PARTIALLY_ACHIEVED' and not notes_val:
                errors.append(f'Efekt {efekt.kod}: wymagane uzasadnienie dla wyniku „Uzyskał/a częściowo"')
            evaluations.append((efekt.id, wynik_val, notes_val))

        if errors:
            for err in errors:
                flash(err, 'danger')
            istniejace = {e.learning_outcome_id: e for e in CommitteeOutcomeEvaluation.query.filter_by(enrollment_id=id).all()}
            dokumenty  = _repo_docs.dla_zapisu_studenta(id, zapis.student_id)
            return render_template('zarzadzanie/komisja/weryfikuj.html',
                                   form=form, zapis=zapis, dokumenty=dokumenty,
                                   efekty=efekty, istniejace=istniejace)

        from core.uslugi.workflow import ZapisFSM, IllegalTransitionError
        try:
            with ZapisFSM.lock(id) as fsm:
                if fsm.zapis.status not in ACTIVE_STATUSES:
                    flash('Wniosek zmienił status podczas przetwarzania — spróbuj ponownie.', 'warning')
                    return redirect(url_for('zarzadzanie.komisja_lista'))

                for outcome_id, wynik_val, notes_val in evaluations:
                    existing = CommitteeOutcomeEvaluation.query.filter_by(
                        enrollment_id=id, learning_outcome_id=outcome_id
                    ).first()
                    if existing:
                        existing.result = AssessmentResult(wynik_val)
                        existing.notes  = notes_val or None
                    else:
                        db.session.add(CommitteeOutcomeEvaluation(
                            enrollment_id=id,
                            learning_outcome_id=outcome_id,
                            result=AssessmentResult(wynik_val),
                            notes=notes_val or None,
                        ))

                komentarz = form.komentarz.data or ''
                fsm.wyslij_do_dyrektora(decision=opinia, actor_id=current_user.id, comment=komentarz)
                db.session.commit()

            _LABELS = {
                'APPROVED':           'Opinia pozytywna',
                'PARTIALLY_APPROVED': 'Opinia częściowo pozytywna',
                'REJECTED':           'Opinia negatywna',
            }
            flash(f'{_LABELS[opinia]} — wniosek przekazany do Dyrektora Instytutu.', 'success')
        except IllegalTransitionError as e:
            flash(str(e), 'danger')
        return redirect(url_for('zarzadzanie.komisja_lista'))

    istniejace = {e.learning_outcome_id: e for e in CommitteeOutcomeEvaluation.query.filter_by(enrollment_id=id).all()}
    dokumenty  = _repo_docs.dla_zapisu_studenta(id, zapis.student_id)
    return render_template('zarzadzanie/komisja/weryfikuj.html',
                           form=form, zapis=zapis, dokumenty=dokumenty,
                           efekty=efekty, istniejace=istniejace)


