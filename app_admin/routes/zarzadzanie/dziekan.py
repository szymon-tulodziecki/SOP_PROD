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
                    UserRole, InternshipStatus, EnrollmentStatus, UploadedDocument, Company,
                    CommitteeOutcomeEvaluation)
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
    page         = request.args.get('page', 1, type=int)
    applications = _repo_zapisow.wnioski_dziekana_strona(strona=page)
    csrf_form    = FlaskForm()
    return render_template('zarzadzanie/dziekan/lista.html', wnioski=applications, csrf_form=csrf_form)


@zarzadzanie_bp.route('/dziekan/<uuid:id>/decyzja', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.DYREKTOR)
def dziekan_decyzja(id):
    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SelectField, SubmitField
    from wtforms.validators import DataRequired, Optional

    enrollment = db.session.get(InternshipEnrollment, id) or abort(404)

    if enrollment.status != EnrollmentStatus.DIRECTOR_APPROVAL:
        flash('Wniosek nie wymaga decyzji Dyrektora Instytutu.', 'warning')
        return redirect(url_for('zarzadzanie.dziekan_lista'))

    class DirectorForm(FlaskForm):
        comment = TextAreaField('Komentarz dyrektora', validators=[Optional()])

    form = DirectorForm()

    if form.validate_on_submit():
        decision = request.form.get('decyzja')
        if decision not in ('APPROVED', 'REJECTED'):
            flash('Wybierz decyzję (jeden z dwóch przycisków).', 'warning')
        else:
            from core.uslugi.workflow import ZapisFSM, IllegalTransitionError
            try:
                with ZapisFSM.lock(id) as fsm:
                    if fsm.zapis.status != EnrollmentStatus.DIRECTOR_APPROVAL:
                        flash('Wniosek zmienił status podczas przetwarzania — spróbuj ponownie.', 'warning')
                        return redirect(url_for('zarzadzanie.dziekan_lista'))

                    comment = form.comment.data or ''
                    if decision == 'APPROVED':
                        fsm.zatwierdz_przez_dyrektora(actor_id=current_user.id, comment=comment)
                        flash('Wniosek zatwierdzony przez Dyrektora Instytutu. Student może kontynuować praktykę.', 'success')
                    else:
                        from core.modele.praktyki import EventType
                        fsm.odrzuc(actor_id=current_user.id,
                                   comment=f"Dyrektor nie wyraził zgody: {comment}",
                                   event_type=EventType.DIRECTOR_DECISION)
                        flash('Wniosek odrzucony przez Dyrektora Instytutu.', 'warning')

                    db.session.commit()
            except IllegalTransitionError as e:
                flash(str(e), 'danger')
            return redirect(url_for('zarzadzanie.dziekan_lista'))

    documents = (
        db.session.query(UploadedDocument)
        .filter_by(enrollment_id=id, is_deleted=False)
        .order_by(UploadedDocument.uploaded_at.desc())
        .all()
    )
    outcomes            = LearningOutcome.query.order_by(LearningOutcome.id).all()
    committee_evaluations = {
        e.learning_outcome_id: e
        for e in CommitteeOutcomeEvaluation.query.filter_by(enrollment_id=id).all()
    }
    return render_template('zarzadzanie/dziekan/decyzja.html',
                           form=form, zapis=enrollment, dokumenty=documents,
                           efekty=outcomes, oceny_komisji=committee_evaluations)
