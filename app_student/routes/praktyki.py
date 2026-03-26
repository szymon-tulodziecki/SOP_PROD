import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DateField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, Optional, Length, Email
from flask_login import login_required, current_user
from app_student.extensions import db
from app_student.models import Praktyka, ZapisPraktyki, StatusPraktyki, StatusZapisu, SciezkaPraktyki, Uzytkownik, RolaUzytkownika, EfektUczenia, HarmonogramPraktyki

praktyki_bp = Blueprint('praktyki', __name__)

class FormularzZapisuKrok1(FlaskForm):
    track_type = SelectField('Ścieżka praktyki', choices=[
        ('STANDARD', 'Standardowa'),
        ('EMPLOYMENT', 'Praca etatowa'),
        ('OWN_BUSINESS', 'Własna działalność gospodarcza')
    ], validators=[DataRequired()])
    
    termin_od = DateField('Data rozpoczęcia', validators=[DataRequired()])
    termin_do = DateField('Data zakończenia', validators=[DataRequired()])
    specjalnosc = StringField('Specjalność', validators=[DataRequired()])
    ubezpieczenie_nw = BooleanField('Posiadam ubezpieczenie NW (wymagane)', validators=[DataRequired()])
    
    # Firma
    firma_nazwa = StringField('Nazwa zakładu pracy', validators=[DataRequired()])
    firma_adres = StringField('Adres (ulica, nr)', validators=[DataRequired()])
    firma_miasto = StringField('Miasto i kod pocztowy', validators=[DataRequired()])
    firma_nip_krs = StringField('NIP / KRS', validators=[Optional()])
    firma_upowazniony_osoba = StringField('Osoba upoważniona do podpisania Porozumienia (Imię i nazwisko)', validators=[DataRequired()])
    firma_upowazniony_stanowisko = StringField('Stanowisko osoby upoważnionej', validators=[DataRequired()])
    
    # ZOPZ
    zopz_imie_nazwisko = StringField('Opiekun Zakładowy (ZOPZ) - Imię i nazwisko', validators=[DataRequired()])
    zopz_stanowisko = StringField('Stanowisko ZOPZ', validators=[DataRequired()])
    zopz_telefon = StringField('Telefon ZOPZ', validators=[DataRequired()])
    zopz_email = StringField('E-mail ZOPZ', validators=[DataRequired(), Email()])
    
    # UOPZ
    uopz_id = SelectField('Wybierz Opiekuna Uczelnianego (UOPZ)', choices=[], validators=[DataRequired()])


@praktyki_bp.route('/')
@login_required
def lista():
    dostepne = db.session.query(Praktyka)\
                 .order_by(Praktyka.rok_uczelniany.desc())\
                 .all()

    zapisane_ids = {
        str(z.internship_id)
        for z in db.session.query(ZapisPraktyki)\
                   .filter_by(student_id=current_user.id).all()
    }

    csrf_form = FlaskForm()
    return render_template('praktyki/lista.html', dostepne=dostepne, zapisane_ids=zapisane_ids, csrf_form=csrf_form)


@praktyki_bp.route('/<uuid:id>/zapisz/krok1', methods=['GET', 'POST'])
@login_required
def zapisz_krok1(id):
    praktyka = db.session.get(Praktyka, id)
    if not praktyka:
        flash('Ta praktyka nie jest dostępna.', 'danger')
        return redirect(url_for('praktyki.lista'))

    istniejacy = db.session.query(ZapisPraktyki).filter_by(
        internship_id=id,
        student_id=current_user.id
    ).first()

    if istniejacy:
        flash('Jesteś już zapisany do tej praktyki (lub w trakcie zapisu). Przejdź do kolejnych kroków.', 'info')
        return redirect(url_for('dashboard.index'))

    form = FormularzZapisuKrok1()

    uopz_list = db.session.query(Uzytkownik).filter_by(role=RolaUzytkownika.UOPZ, is_active=True).order_by(Uzytkownik.last_name).all()
    form.uopz_id.choices = [('', '--- Wybierz UOPZ ---')] + [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]

    if form.validate_on_submit():
        if not form.ubezpieczenie_nw.data:
            flash('Ubezpieczenie NW jest wymagane przed startem.', 'danger')
            return render_template('praktyki/krok1.html', form=form, praktyka=praktyka)

        zapis = ZapisPraktyki(
            id            = uuid.uuid4(),
            internship_id = id,
            student_id    = current_user.id,
            status        = StatusZapisu.PENDING,
            track_type    = SciezkaPraktyki[form.track_type.data],
            termin_od     = form.termin_od.data,
            termin_do     = form.termin_do.data,
            specjalnosc   = form.specjalnosc.data,
            ubezpieczenie_nw = form.ubezpieczenie_nw.data,
            firma_nazwa   = form.firma_nazwa.data,
            firma_adres   = form.firma_adres.data,
            firma_miasto  = form.firma_miasto.data,
            firma_nip_krs = form.firma_nip_krs.data,
            firma_upowazniony_osoba = form.firma_upowazniony_osoba.data,
            firma_upowazniony_stanowisko = form.firma_upowazniony_stanowisko.data,
            zopz_imie_nazwisko = form.zopz_imie_nazwisko.data,
            zopz_stanowisko = form.zopz_stanowisko.data,
            zopz_telefon = form.zopz_telefon.data,
            zopz_email = form.zopz_email.data,
            uopz_id = form.uopz_id.data
        )
        db.session.add(zapis)
        db.session.commit()

        flash(f'Zapisano wstępne dane. Przejdź do planowania harmonogramu.', 'success')
        return redirect(url_for('praktyki.zapisz_krok2', id=zapis.id))

    return render_template('praktyki/krok1.html', form=form, praktyka=praktyka)


@praktyki_bp.route('/zgloszenie/<uuid:id>/krok2', methods=['GET', 'POST'])
@login_required
def zapisz_krok2(id):
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
        
    efekty = db.session.query(EfektUczenia).order_by(EfektUczenia.id).all()
        
    if request.method == 'POST':
        # Czyszczenie starego jeśli student wraca z jakiegoś powodu
        db.session.query(HarmonogramPraktyki).filter_by(enrollment_id=zapis.id).delete()
        
        suma_dni = 0
        nowe_wiersze = []
        for e in efekty:
            dz = request.form.get(f'dzial_{e.id}', '')
            pr = request.form.get(f'prace_{e.id}', '')
            dni_str = request.form.get(f'dni_{e.id}', '0')
            try:
                dni = int(dni_str)
            except Exception:
                dni = 0
                
            if dz.strip() and pr.strip():
                nowe_wiersze.append(HarmonogramPraktyki(
                    id=uuid.uuid4(),
                    enrollment_id=zapis.id,
                    learning_outcome_id=e.id,
                    nazwa_dzialu=dz,
                    przykladowe_prace=pr,
                    liczba_dni=dni
                ))
                suma_dni += dni
                
        db.session.add_all(nowe_wiersze)
        db.session.commit()
        
        if zapis.track_type.value != 'STANDARD':
            flash('Harmonogram zapisany. Przejdź do uzasadnienia ścieżki zawodowej.', 'success')
            return redirect(url_for('praktyki.zapisz_krok3', id=zapis.id))
        else:
            flash('Wniosek został w pełni zapisany. Oczekuje teraz na akceptację UOPZ.', 'success')
            return redirect(url_for('dashboard.index'))
            
    csrf_form = FlaskForm()
    
    return render_template('praktyki/krok2.html', zapis=zapis, efekty=efekty, csrf_form=csrf_form)


class FormularzZapisuKrok3(FlaskForm):
    uzasadnienie = TextAreaField('Uzasadnienie wniosku', validators=[DataRequired()])
    zalaczniki = StringField('Załączane dokumenty (wymień)', validators=[DataRequired()])

@praktyki_bp.route('/zgloszenie/<uuid:id>/krok3', methods=['GET', 'POST'])
@login_required
def zapisz_krok3(id):
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
        
    if zapis.track_type.value == 'STANDARD':
        return redirect(url_for('dashboard.index'))
        
    form = FormularzZapisuKrok3()
    
    if form.validate_on_submit():
        zapis.uzasadnienie_sciezki = form.uzasadnienie.data
        zapis.zalaczniki_sciezki = form.zalaczniki.data
        db.session.commit()
        
        flash('Wniosek o ścieżkę zawodową został zapisany! Oczekuje na zatwierdzenie.', 'success')
        return redirect(url_for('dashboard.index'))
        
    return render_template('praktyki/krok3.html', form=form, zapis=zapis)