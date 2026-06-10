from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms.validators import Optional

from core.models import (InternshipEnrollment, UserRole, EnrollmentStatus)
from core.extensions import db, limiter
from core.services.internships import InternshipService
_serwis_praktyk = InternshipService()
from core.auth import roles_required
from core.presenters import (committee_decision_badge, outcome_result_badge,
                             outcome_result_counts, path_label)
from core.services.workflow import IllegalTransitionError
from core.repositories import EnrollmentRepository, StudentDocumentRepository, OutcomeRepository, AssessmentRepository

_repo_zapisow = EnrollmentRepository()
_repo_docs    = StudentDocumentRepository()
_repo_efektow = OutcomeRepository()
_repo_ocen    = AssessmentRepository()

_ROUTE_DYREKTOR_LISTA = 'zarzadzanie.dyrektor_lista'

from . import zarzadzanie_bp


# ── Dyrektor Instytutu ────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/dyrektor', methods=['GET'])
@roles_required(UserRole.ADMIN, UserRole.DYREKTOR)
def dyrektor_lista():
    page         = request.args.get('page', 1, type=int)
    applications = _repo_zapisow.wnioski_dyrektora_strona(strona=page)
    csrf_form    = FlaskForm()
    return render_template('zarzadzanie/dyrektor/lista.html', wnioski=applications, csrf_form=csrf_form)


@zarzadzanie_bp.route('/dyrektor/<uuid:id>/decision', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN, UserRole.DYREKTOR)
@limiter.limit("60 per hour", methods=['POST'])
def dyrektor_decyzja(id):
    enrollment = _repo_zapisow.znajdz_po_id(id) or abort(404)

    if enrollment.status != EnrollmentStatus.DIRECTOR_APPROVAL:
        flash('Wniosek nie wymaga decyzji Dyrektora Instytutu.', 'warning')
        return redirect(url_for(_ROUTE_DYREKTOR_LISTA))

    class DirectorForm(FlaskForm):
        comment = TextAreaField('Komentarz dyrektora', validators=[Optional()])

    form = DirectorForm()

    if form.validate_on_submit():
        decision = request.form.get('decision')
        if decision not in ('APPROVED', 'REJECTED'):
            flash('Wybierz decyzję (jeden z dwóch przycisków).', 'warning')
        else:
            comment = form.comment.data or ''
            try:
                _serwis_praktyk.apply_director_decision(id, decision, current_user.id, comment)
                if decision == 'APPROVED':
                    flash('Wniosek zatwierdzony przez Dyrektora Instytutu. Student może kontynuować praktykę.', 'success')
                else:
                    flash('Wniosek odrzucony przez Dyrektora Instytutu.', 'warning')
            except IllegalTransitionError as e:
                flash(str(e), 'danger')
            return redirect(url_for(_ROUTE_DYREKTOR_LISTA))

    documents             = _repo_docs.dokumenty_zapisu(id)
    outcomes              = _repo_efektow.wszystkie()
    committee_evaluations = _repo_ocen.dla_komisji_dict(id)
    efekty_wiersze = []
    for lo in outcomes:
        ev = committee_evaluations.get(lo.id)
        efekty_wiersze.append({
            'efekt': lo,
            'ocena': ev,
            'badge': outcome_result_badge(ev.result.value) if ev else None,
        })
    return render_template('zarzadzanie/dyrektor/decyzja.html',
                           form=form, zapis=enrollment, dokumenty=documents,
                           oceny_komisji=committee_evaluations,
                           efekty_wiersze=efekty_wiersze,
                           oceny_stats=outcome_result_counts(committee_evaluations),
                           sciezka_label=path_label(enrollment.path_type.value),
                           opinia_komisji=committee_decision_badge(enrollment.committee_decision))
