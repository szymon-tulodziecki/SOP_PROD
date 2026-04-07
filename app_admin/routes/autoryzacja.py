from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email, Length
from werkzeug.security import check_password_hash

from core.modele import Uzytkownik, RolaUzytkownika
from core.extensions import db
from sqlalchemy.exc import SQLAlchemyError, OperationalError

auth_bp = Blueprint('auth', __name__)

class FormularzLogowania(FlaskForm):
    email = StringField('Adres e-mail',
                    validators=[DataRequired('Podaj adres e-mail.'),
                                Email('Podaj poprawny adres e-mail.'),
                                Length(max=255)])
    haslo = PasswordField('Hasło',
                    validators=[DataRequired('Podaj hasło.'),
                                Length(min=1, max=128)])
    zapamietaj = BooleanField('Zapamiętaj mnie')

@auth_bp.route('/', methods=['GET'])
@auth_bp.route('/logowanie', methods=['GET', 'POST'])
def logowanie():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = FormularzLogowania()

    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        try:
            uzytkownik = db.session.query(Uzytkownik).filter_by(email=email).first()
        except (OperationalError, SQLAlchemyError) as e:
            current_app.logger.exception('Błąd połączenia z bazą podczas logowania')
            flash('Błąd połączenia z bazą danych. Spróbuj ponownie później.', 'danger')
            return render_template('auth/logowanie.html', form=form)

        if uzytkownik and uzytkownik.is_active:
            if check_password_hash(uzytkownik.password_hash, form.haslo.data):
                if uzytkownik.role == RolaUzytkownika.STUDENT:
                    flash('Konto studenckie nie ma dostępu do panelu admina.', 'danger')
                    return render_template('auth/logowanie.html', form=form)

                login_user(uzytkownik, remember=form.zapamietaj.data)

                next_page = request.args.get('next')
                return redirect(next_page) if next_page and next_page.startswith('/') else redirect(url_for('dashboard.index'))

        flash('Nieprawidłowy adres e-mail lub hasło.', 'danger')

    return render_template('auth/logowanie.html', form=form)

@auth_bp.route('/wylogowanie', methods=['GET', 'POST'])
@login_required
def wylogowanie():
    logout_user()
    flash('Wylogowano pomyślnie.', 'success')
    return redirect(url_for('auth.logowanie'))

def wymaga_roli(*dozwolone_role):
    def dekorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in dozwolone_role:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return dekorator

@auth_bp.route('/zmien-haslo', methods=['GET', 'POST'])
@login_required
def zmien_haslo():
    from flask_wtf import FlaskForm
    from wtforms import PasswordField
    from wtforms.validators import DataRequired, Length, EqualTo
    from werkzeug.security import generate_password_hash

    class FormularzZmianyHasla(FlaskForm):
        nowe_haslo    = PasswordField('Nowe hasło', validators=[DataRequired(), Length(min=8, max=128)])
        potwierdzenie = PasswordField('Powtórz hasło', validators=[EqualTo('nowe_haslo', message='Hasła muszą być identyczne.')])

    form = FormularzZmianyHasla()
    if form.validate_on_submit():
        current_user.password_hash = generate_password_hash(form.nowe_haslo.data)
        current_user.wymagana_zmiana_hasla = False
        db.session.commit()
        flash('Hasło zostało zmienione. Możesz korzystać z systemu.', 'success')
        return redirect(url_for('dashboard.index'))
    return render_template('auth/zmien_haslo.html', form=form)
