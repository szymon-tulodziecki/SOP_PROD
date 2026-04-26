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
from wtforms import StringField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError
from werkzeug.security import generate_password_hash

from core.modele import (User, Student, Internship, InternshipEnrollment, InternshipSchedule, LearningOutcome,
                    UserRole, InternshipStatus, EnrollmentStatus, UploadedDocument, Company,
                    CommitteeOutcomeEvaluation, AssessmentResult)
from core.extensions import db
from core.uslugi import UslugaUzytkownikow as _UslugaUzytkownikow, SerwisKomisji
_serwis_uzytkownikow = _UslugaUzytkownikow()
from core.autoryzacja import wymaga_roli
from core.uslugi.workflow import ZapisFSM, IllegalTransitionError
from core.repozytoria import RepozytoriumZapisow, RepozytoriumDokumentowStudenta

_repo_zapisow = RepozytoriumZapisow()
_repo_docs    = RepozytoriumDokumentowStudenta()

from . import zarzadzanie_bp
from .formularze import *

# ── Komisja weryfikująca ──────────────────────────────────────────────────────

@zarzadzanie_bp.route('/komisja')
@wymaga_roli(UserRole.ADMIN, UserRole.KOMISJA)
def komisja_lista():
    page        = request.args.get('page', 1, type=int)
    applications = _repo_zapisow.wnioski_komisja_strona(strona=page)
    csrf_form   = FlaskForm()
    return render_template('zarzadzanie/komisja/lista.html', wnioski=applications, csrf_form=csrf_form)


@zarzadzanie_bp.route('/komisja/<uuid:id>/weryfikuj', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.KOMISJA)
def komisja_weryfikuj(id):
    enrollment = db.session.get(InternshipEnrollment, id) or abort(404)

    if enrollment.status not in (EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.REVISION_REQUIRED):
        flash('Wniosek nie wymaga weryfikacji komisji.', 'warning')
        return redirect(url_for('zarzadzanie.komisja_lista'))

    class CommitteeForm(FlaskForm):
        comment = TextAreaField('Komentarz ogólny komisji', validators=[Optional()])

    form    = CommitteeForm()
    outcomes = LearningOutcome.query.order_by(LearningOutcome.id).all()

    ACTIVE_STATUSES = (EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.AWAITING_APPROVAL)

    if form.validate_on_submit():
        if enrollment.status not in ACTIVE_STATUSES:
            flash('Wniosek nie jest w stanie umożliwiającym decyzję komisji.', 'warning')
            return redirect(url_for('zarzadzanie.komisja_lista'))

        committee_opinion = request.form.get('opinia')
        if committee_opinion not in ('APPROVED', 'PARTIALLY_APPROVED', 'REJECTED'):
            flash('Wybierz opinię komisji (jeden z trzech przycisków).', 'warning')
            existing_evaluations = {e.learning_outcome_id: e for e in CommitteeOutcomeEvaluation.query.filter_by(enrollment_id=id).all()}
            documents            = _repo_docs.dla_zapisu_studenta(id, enrollment.student_id)
            return render_template('zarzadzanie/komisja/weryfikuj.html',
                                   form=form, zapis=enrollment, dokumenty=documents,
                                   efekty=outcomes, istniejace=existing_evaluations)

        errors, evaluations = SerwisKomisji.waliduj_oceny_efektow(outcomes, request.form)

        if errors:
            for err in errors:
                flash(err, 'danger')
            existing_evaluations = {e.learning_outcome_id: e for e in CommitteeOutcomeEvaluation.query.filter_by(enrollment_id=id).all()}
            documents            = _repo_docs.dla_zapisu_studenta(id, enrollment.student_id)
            return render_template('zarzadzanie/komisja/weryfikuj.html',
                                   form=form, zapis=enrollment, dokumenty=documents,
                                   efekty=outcomes, istniejace=existing_evaluations)

        try:
            with ZapisFSM.lock(id) as fsm:
                if fsm.zapis.status not in ACTIVE_STATUSES:
                    flash('Wniosek zmienił status podczas przetwarzania — spróbuj ponownie.', 'warning')
                    return redirect(url_for('zarzadzanie.komisja_lista'))

                for outcome_id, result_val, notes_val in evaluations:
                    existing = CommitteeOutcomeEvaluation.query.filter_by(
                        enrollment_id=id, learning_outcome_id=outcome_id
                    ).first()
                    if existing:
                        existing.result = AssessmentResult(result_val)
                        existing.notes  = notes_val or None
                    else:
                        db.session.add(CommitteeOutcomeEvaluation(
                            enrollment_id=id,
                            learning_outcome_id=outcome_id,
                            result=AssessmentResult(result_val),
                            notes=notes_val or None,
                        ))

                comment = form.comment.data or ''
                fsm.wyslij_do_dyrektora(decision=committee_opinion, actor_id=current_user.id, comment=comment)
                db.session.commit()

            _LABELS = {
                'APPROVED':           'Opinia pozytywna',
                'PARTIALLY_APPROVED': 'Opinia częściowo pozytywna',
                'REJECTED':           'Opinia negatywna',
            }
            flash(f'{_LABELS[committee_opinion]} — wniosek przekazany do Dyrektora Instytutu.', 'success')
        except IllegalTransitionError as e:
            flash(str(e), 'danger')
        return redirect(url_for('zarzadzanie.komisja_lista'))

    existing_evaluations = {e.learning_outcome_id: e for e in CommitteeOutcomeEvaluation.query.filter_by(enrollment_id=id).all()}
    documents            = _repo_docs.dla_zapisu_studenta(id, enrollment.student_id)
    return render_template('zarzadzanie/komisja/weryfikuj.html',
                           form=form, zapis=enrollment, dokumenty=documents,
                           efekty=outcomes, istniejace=existing_evaluations)
