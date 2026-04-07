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

# ── Komisja weryfikująca ──────────────────────────────────────────────────────

@zarzadzanie_bp.route('/komisja')
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def komisja_lista():
    strona = request.args.get('page', 1, type=int)
    from sqlalchemy import or_
    from sqlalchemy import exists
    from core.modele import ZdarzenieProces, TypZdarzenia
    ma_komentarz_uopz = exists().where(
        (ZdarzenieProces.zapis_id == ZapisPraktyki.id) &
        (ZdarzenieProces.typ == TypZdarzenia.UOPZ_KOMENTARZ) &
        ZdarzenieProces.komentarz.isnot(None)
    )
    q = db.session.query(ZapisPraktyki)\
          .join(Uzytkownik, ZapisPraktyki.student_id == Uzytkownik.id)\
          .filter(ZapisPraktyki.sciezka.in_(['EMPLOYMENT', 'OWN_BUSINESS']))\
          .filter(or_(
              ZapisPraktyki.status == StatusZapisu.COMMISSION_REVIEW,
              (ZapisPraktyki.status == StatusZapisu.AWAITING_APPROVAL) & ma_komentarz_uopz,
          ))
    wnioski   = q.order_by(ZapisPraktyki.enrolled_at.desc()).paginate(page=strona, per_page=25, error_out=False)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/komisja/lista.html', wnioski=wnioski, csrf_form=csrf_form)


@zarzadzanie_bp.route('/komisja/<uuid:id>/weryfikuj', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def komisja_weryfikuj(id):
    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SelectField, SubmitField
    from wtforms.validators import DataRequired, Optional

    zapis = db.session.get(ZapisPraktyki, id) or abort(404)

    if zapis.status != StatusZapisu.COMMISSION_REVIEW:
        flash('Wniosek nie wymaga weryfikacji komisji.', 'warning')
        return redirect(url_for('zarzadzanie.komisja_lista'))

    class FormularzKomisji(FlaskForm):
        decyzja   = SelectField('Decyzja komisji', choices=[
            ('APPROVED',           'Zatwierdzam - kieruję do dziekana'),
            ('PARTIALLY_APPROVED', 'Zatwierdzam częściowo - wymaga uzupełnień'),
            ('REJECTED',           'Odrzucam wniosek'),
        ], validators=[DataRequired()])
        komentarz = TextAreaField('Komentarz komisji', validators=[Optional()])
        submit    = SubmitField('Zapisz decyzję')

    form = FormularzKomisji()

    if form.validate_on_submit():
        from core.modele import ZdarzenieProces, TypZdarzenia
        from datetime import datetime

        if form.decyzja.data == 'APPROVED':
            decyzja_db = 'APPROVED'
            zapis.status = StatusZapisu.DEAN_APPROVAL
            flash('Wniosek zatwierdzony i przekazany do dziekana.', 'success')
        elif form.decyzja.data == 'PARTIALLY_APPROVED':
            decyzja_db = 'PARTIALLY_APPROVED'
            zapis.status = StatusZapisu.AWAITING_APPROVAL
            db.session.add(ZdarzenieProces(
                zapis_id=zapis.id, typ=TypZdarzenia.UOPZ_KOMENTARZ,
                komentarz=f"Komisja: {form.komentarz.data}",
                wykonane_przez_id=current_user.id, wykonano_o=datetime.utcnow(),
            ))
            flash('Wniosek wymaga uzupełnień - student zostanie powiadomiony.', 'info')
        else:
            decyzja_db = 'REJECTED'
            zapis.status = StatusZapisu.REJECTED
            db.session.add(ZdarzenieProces(
                zapis_id=zapis.id, typ=TypZdarzenia.UOPZ_KOMENTARZ,
                komentarz=f"Wniosek odrzucony przez komisję: {form.komentarz.data}",
                wykonane_przez_id=current_user.id, wykonano_o=datetime.utcnow(),
            ))
            flash('Wniosek został odrzucony.', 'warning')

        db.session.add(ZdarzenieProces(
            zapis_id=zapis.id, typ=TypZdarzenia.KOMISJA_DECYZJA,
            decyzja=decyzja_db, komentarz=form.komentarz.data,
            wykonane_przez_id=current_user.id, wykonano_o=datetime.utcnow(),
        ))
        db.session.commit()
        return redirect(url_for('zarzadzanie.komisja_lista'))

    dokumenty = db.session.query(UploadedDocument)\
                  .filter_by(zapis_id=id)\
                  .order_by(UploadedDocument.przeslano_o.desc())\
                  .all()
    return render_template('zarzadzanie/komisja/weryfikuj.html',
                           form=form, zapis=zapis, dokumenty=dokumenty)


