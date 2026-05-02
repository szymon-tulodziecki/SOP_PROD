from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms.validators import Optional

from core.autoryzacja import roles_required
from core.extensions import db
from core.modele import AssessmentResult, EnrollmentStatus, UserRole
from core.repozytoria import (
    AssessmentRepository,
    EnrollmentRepository,
    OutcomeRepository,
    StudentDocumentRepository,
)
from core.uslugi import SerwisKomisji
from core.uslugi.workflow import IllegalTransitionError, ZapisFSM

from . import zarzadzanie_bp

_repo_zapisow = EnrollmentRepository()
_repo_docs    = StudentDocumentRepository()
_repo_efektow = OutcomeRepository()
_repo_ocen    = AssessmentRepository()

_ROUTE_KOMISJA_LISTA = 'zarzadzanie.komisja_lista'
_TPL_WERYFIKUJ       = 'zarzadzanie/komisja/weryfikuj.html'
_ACTIVE_COMMITTEE_STATUSES = (
    EnrollmentStatus.COMMISSION_REVIEW,
    EnrollmentStatus.AWAITING_APPROVAL,
)
_REVIEWABLE_COMMITTEE_STATUSES = (
    *_ACTIVE_COMMITTEE_STATUSES,
    EnrollmentStatus.REVISION_REQUIRED,
)
_COMMITTEE_DECISION_LABELS = {
    'APPROVED':           'Opinia pozytywna',
    'PARTIALLY_APPROVED': 'Opinia częściowo pozytywna',
    'REJECTED':           'Opinia negatywna',
}
_COMMITTEE_DECISIONS = tuple(_COMMITTEE_DECISION_LABELS)


class CommitteeForm(FlaskForm):
    comment = TextAreaField('Komentarz ogólny komisji', validators=[Optional()])


@zarzadzanie_bp.route('/komisja', methods=['GET'])
@roles_required(UserRole.ADMIN, UserRole.KOMISJA)
def komisja_lista():
    page = request.args.get('page', 1, type=int)
    applications = _repo_zapisow.wnioski_komisja_strona(strona=page)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/komisja/lista.html', wnioski=applications, csrf_form=csrf_form)


def _render_weryfikuj_komisji(form, enrollment, outcomes, enrollment_id):
    ev = _repo_ocen.dla_komisji_dict(enrollment_id)
    doc = _repo_docs.dla_zapisu_studenta(enrollment_id, enrollment.student_id)
    return render_template(
        _TPL_WERYFIKUJ,
        form=form,
        zapis=enrollment,
        dokumenty=doc,
        efekty=outcomes,
        istniejace=ev,
    )


def _zapisz_oceny_komisji(enrollment_id, evaluations):
    for outcome_id, result_val, notes_val in evaluations:
        _repo_ocen.zapisz_ocene_komisji(
            enrollment_id=enrollment_id,
            outcome_id=outcome_id,
            result=AssessmentResult(result_val),
            notes=notes_val or None,
        )


def _przekaz_do_dyrektora(enrollment_id, committee_opinion, comment, evaluations):
    with ZapisFSM.lock(enrollment_id) as fsm:
        if fsm.zapis.status not in _ACTIVE_COMMITTEE_STATUSES:
            flash('Wniosek zmienił status podczas przetwarzania - spróbuj ponownie.', 'warning')
            return False
        _zapisz_oceny_komisji(enrollment_id, evaluations)
        fsm.wyslij_do_dyrektora(decision=committee_opinion, actor_id=current_user.id, comment=comment)
        db.session.commit()
    return True


@zarzadzanie_bp.route('/komisja/<uuid:id>/weryfikuj', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN, UserRole.KOMISJA)
def komisja_weryfikuj(id):
    enrollment = _repo_zapisow.znajdz_po_id(id) or abort(404)

    if enrollment.status not in _REVIEWABLE_COMMITTEE_STATUSES:
        flash('Wniosek nie wymaga weryfikacji komisji.', 'warning')
        return redirect(url_for(_ROUTE_KOMISJA_LISTA))

    form = CommitteeForm()
    outcomes = _repo_efektow.wszystkie()

    if not form.validate_on_submit():
        return _render_weryfikuj_komisji(form, enrollment, outcomes, id)

    if enrollment.status not in _ACTIVE_COMMITTEE_STATUSES:
        flash('Wniosek nie jest w stanie umożliwiającym decyzję komisji.', 'warning')
        return redirect(url_for(_ROUTE_KOMISJA_LISTA))

    committee_opinion = request.form.get('opinia')
    if committee_opinion not in _COMMITTEE_DECISIONS:
        flash('Wybierz opinię komisji (jeden z trzech przycisków).', 'warning')
        return _render_weryfikuj_komisji(form, enrollment, outcomes, id)

    errors, evaluations = SerwisKomisji.waliduj_oceny_efektow(outcomes, request.form)
    if errors:
        for err in errors:
            flash(err, 'danger')
        return _render_weryfikuj_komisji(form, enrollment, outcomes, id)

    try:
        if _przekaz_do_dyrektora(id, committee_opinion, form.comment.data or '', evaluations):
            label = _COMMITTEE_DECISION_LABELS[committee_opinion]
            flash(f'{label} - wniosek przekazany do Dyrektora Instytutu.', 'success')
    except IllegalTransitionError as e:
        flash(str(e), 'danger')
    return redirect(url_for(_ROUTE_KOMISJA_LISTA))
