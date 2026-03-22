from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo
from werkzeug.security import check_password_hash, generate_password_hash

from app_student.models import Uzytkownik, RolaUzytkownika
from app_student.extensions import db

auth_bp = Blueprint('auth', __name__)


class FormularzLogowania(FlaskForm):
    email      = StringField('E-mail',  validators=[DataRequired(), Email(), Length(max=255)])
    haslo      = PasswordField('Hasło', validators=[DataRequired(), Length(min=1, max=128)])
    zapamietaj = BooleanField('Zapamiętaj mnie')


class FormularzZmianyHasla(FlaskForm):
    nowe_haslo    = PasswordField('Nowe hasło',    validators=[DataRequired(), Length(min=8, max=128)])
    potwierdzenie = PasswordField('Powtórz hasło', validators=[
        DataRequired(),
        EqualTo('nowe_haslo', message='Hasła muszą być identyczne.')
    ])


@auth_bp.route('/', methods=['GET'])
@auth_bp.route('/logowanie', methods=['GET', 'POST'])
def logowanie():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = FormularzLogowania()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        u = db.session.query(Uzytkownik).filter_by(email=email).first()

        if u and u.is_active and check_password_hash(u.password_hash, form.haslo.data):
            if u.role != RolaUzytkownika.STUDENT:
                flash('Ten panel jest tylko dla studentów.', 'danger')
                return render_template('auth/logowanie.html', form=form)

            login_user(u, remember=form.zapamietaj.data)
            next_page = request.args.get('next')
            return redirect(next_page if next_page and next_page.startswith('/') else url_for('dashboard.index'))

        flash('Nieprawidłowy adres e-mail lub hasło.', 'danger')

    return render_template('auth/logowanie.html', form=form)


@auth_bp.route('/wylogowanie', methods=['GET', 'POST'])
@login_required
def wylogowanie():
    logout_user()
    flash('Wylogowano pomyślnie.', 'success')
    return redirect(url_for('auth.logowanie'))


@auth_bp.route('/zmien-haslo', methods=['GET', 'POST'])
@login_required
def zmien_haslo():
    form = FormularzZmianyHasla()
    if form.validate_on_submit():
        current_user.password_hash         = generate_password_hash(form.nowe_haslo.data)
        current_user.wymagana_zmiana_hasla = False
        db.session.commit()
        flash('Hasło zostało zmienione.', 'success')
        return redirect(url_for('dashboard.index'))
    return render_template('auth/zmien_haslo.html', form=form)
