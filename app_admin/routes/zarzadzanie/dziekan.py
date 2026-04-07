import uuid
import csv
import io
import datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError
from werkzeug.security import generate_password_hash

from core.modele import (Uzytkownik, Student, Praktyka, ZapisPraktyki, HarmonogramPraktyki, EfektUczenia,
                    RolaUzytkownika, StatusPraktyki, StatusZapisu, UploadedDocument, Firma)
from core.extensions import db
from core.uslugi import UslugaUzytkownikow as _UslugaUzytkownikow
_serwis_uzytkownikow = _UslugaUzytkownikow()
from core.autoryzacja import wymaga_roli

from . import zarzadzanie_bp
from .formularze import *

# ── Dziekan ───────────────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/dziekan')
@wymaga_roli(RolaUzytkownika.ADMIN)
def dziekan_lista():
    strona = request.args.get('page', 1, type=int)
    q = db.session.query(ZapisPraktyki)\
          .join(Uzytkownik, ZapisPraktyki.student_id == Uzytkownik.id)\
          .filter(ZapisPraktyki.status == StatusZapisu.DEAN_APPROVAL)\
          .filter(ZapisPraktyki.sciezka.in_(['EMPLOYMENT', 'OWN_BUSINESS']))
    wnioski   = q.order_by(ZapisPraktyki.enrolled_at.desc()).paginate(page=strona, per_page=25, error_out=False)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/dziekan/lista.html', wnioski=wnioski, csrf_form=csrf_form)


@zarzadzanie_bp.route('/dziekan/<uuid:id>/decyzja', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def dziekan_decyzja(id):
    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SelectField, SubmitField
    from wtforms.validators import DataRequired, Optional

    zapis = db.session.get(ZapisPraktyki, id) or abort(404)

    if zapis.status != StatusZapisu.DEAN_APPROVAL:
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
        zapis.decyzja_dziekana   = form.decyzja.data
        zapis.komentarze_dziekana = form.komentarz.data
        zapis.decyzja_dziekana_o  = db.func.current_timestamp()

        if form.decyzja.data == 'APPROVED':
            zapis.status = StatusZapisu.IN_PROGRESS
            flash('Wniosek zatwierdzony przez dziekana. Student może kontynuować praktykę.', 'success')
        else:
            zapis.status          = StatusZapisu.REJECTED
            zapis.komentarze_uopz = f"Dziekan nie wyraził zgody: {form.komentarz.data}"
            flash('Wniosek odrzucony przez dziekana.', 'warning')

        db.session.commit()
        return redirect(url_for('zarzadzanie.dziekan_lista'))

    return render_template('zarzadzanie/dziekan/decyzja.html', form=form, zapis=zapis)


