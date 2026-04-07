import uuid
import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, make_response
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DateField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, Optional, Length, Email, ValidationError
import re
from flask_login import login_required, current_user
from core.extensions import db
import httpx
from core.modele import Praktyka, ZapisPraktyki, StatusPraktyki, StatusZapisu, SciezkaPraktyki, Uzytkownik, RolaUzytkownika, EfektUczenia, HarmonogramPraktyki, Firma, IndywidualnyProgram, StatusDokumentu, DokumentPrzeslany

praktyki_bp = Blueprint('praktyki', __name__)


# ═══════════════════════════════════════════════════════════
# NOWE FORMULARZE KREATORA
# ═══════════════════════════════════════════════════════════

class FormularzSciezka(FlaskForm):
    """Krok 1: Tylko wybór ścieżki."""
    track_type = SelectField('Ścieżka praktyki', choices=[
        ('STANDARD',     'A — Standardowa praktyka'),
        ('EMPLOYMENT',   'B — Praca etatowa / staż'),
        ('OWN_BUSINESS', 'C — Własna działalność gospodarcza'),
    ], validators=[DataRequired(message='Wybierz ścieżkę.')])


class FormularzDaneFirmy(FlaskForm):
    """Krok 2A: Dane zakładu pracy + ZOPZ + terminy (tylko ścieżka A)."""
    # Terminy i dane podstawowe
    termin_od   = DateField('Data rozpoczęcia', validators=[DataRequired(message='Podaj datę.')])
    termin_do   = DateField('Data zakończenia', validators=[DataRequired(message='Podaj datę.')])
    uopz_id     = SelectField('Opiekun uczelniany (UOPZ)', choices=[], validators=[Optional()])
    ubezpieczenie_nw = BooleanField('Posiadam ubezpieczenie NW na czas trwania praktyki')

    # Tryb znalezienia miejsca
    firma_typ  = SelectField('Jak znalazłeś/-aś miejsce praktyki?', choices=[
        ('database', 'Uczelnia kieruje do zakładu (firma ma umowę z ANS)'),
        ('custom',   'Sam/a znalazłem/-am miejsce (wymaga Zał. 9 i Zał. 1)'),
    ], validators=[DataRequired()])
    firma_id   = SelectField('Wybierz firmę z listy', choices=[], validators=[Optional()])

    firma_nazwa                  = StringField('Nazwa zakładu pracy', validators=[Optional(), Length(max=255)])
    firma_adres                  = StringField('Adres (ulica, nr)', validators=[Optional(), Length(max=255)])
    firma_miasto                 = StringField('Miasto i kod pocztowy', validators=[Optional(), Length(max=100)])
    firma_nip_krs                = StringField('NIP / KRS', validators=[Optional(), Length(max=50)])
    firma_upowazniony_osoba      = StringField('Osoba upoważniona do podpisania porozumienia', validators=[Optional(), Length(max=255)])
    firma_upowazniony_stanowisko = StringField('Stanowisko osoby upoważnionej', validators=[Optional(), Length(max=255)])

    zopz_imie_nazwisko = StringField('Opiekun zakładowy (ZOPZ) — imię i nazwisko', validators=[Optional(), Length(max=255)])
    zopz_stanowisko    = StringField('Stanowisko ZOPZ', validators=[Optional(), Length(max=255)])
    zopz_telefon       = StringField('Telefon ZOPZ', validators=[Optional(), Length(max=50)])
    zopz_email         = StringField('E-mail ZOPZ', validators=[Optional(), Email(message='Nieprawidłowy email.')])

    def validate_firma_miasto(self, field):
        if not field.data:
            return
        if re.fullmatch(r'\d{2}-\d{3}', field.data.strip()):
            raise ValidationError('Podaj nazwę miasta, nie kod pocztowy. Kod pocztowy możesz dołączyć do adresu.')

    def validate_zopz_imie_nazwisko(self, field):
        if not field.data:
            return
        parts = field.data.strip().split()
        if len(parts) < 2:
            raise ValidationError('Podaj imię i nazwisko (co najmniej dwa wyrazy).')
        if any(char.isdigit() for char in field.data):
            raise ValidationError('Imię i nazwisko nie może zawierać cyfr.')

    def validate_firma_upowazniony_osoba(self, field):
        if not field.data:
            return
        parts = field.data.strip().split()
        if len(parts) < 2:
            raise ValidationError('Podaj imię i nazwisko osoby upoważnionej (co najmniej dwa wyrazy).')
        if any(char.isdigit() for char in field.data):
            raise ValidationError('Imię i nazwisko nie może zawierać cyfr.')


class FormularzWniosek(FlaskForm):
    """Krok 2B/C: Wniosek dla ścieżek B i C."""
    pracodawca_nazwa    = StringField('Nazwa pracodawcy / firmy', validators=[DataRequired(message='Podaj nazwę.'), Length(max=255)])
    pracodawca_adres    = StringField('Adres', validators=[Optional(), Length(max=255)])
    pracodawca_miasto   = StringField('Miasto', validators=[Optional(), Length(max=100)])
    stanowisko          = StringField('Stanowisko / zakres działalności', validators=[DataRequired(message='Podaj stanowisko.'), Length(max=255)])
    uzasadnienie        = TextAreaField('Uzasadnienie wniosku', validators=[DataRequired(message='Napisz uzasadnienie.'), Length(max=2000)])


# ═══════════════════════════════════════════════════════════
# NOWE ROUTE KREATORA
# ═══════════════════════════════════════════════════════════

@praktyki_bp.route('/<uuid:id>/kreator/sciezka', methods=['GET', 'POST'])
@login_required
def kreator_sciezka(id):
    """Krok 1: Wybór ścieżki."""
    praktyka = db.session.get(Praktyka, id)
    if not praktyka:
        flash('Praktyka niedostępna.', 'danger')
        return redirect(url_for('praktyki.lista'))

    istniejacy = db.session.query(ZapisPraktyki).filter_by(
        praktyka_id=id, student_id=current_user.id
    ).filter(ZapisPraktyki.status == StatusZapisu.PENDING).first()

    form = FormularzSciezka()

    if form.validate_on_submit():
        if istniejacy:
            zapis = istniejacy
        else:
            zapis = ZapisPraktyki(id=uuid.uuid4(), praktyka_id=id,
                                   student_id=current_user.id, status=StatusZapisu.PENDING)
            db.session.add(zapis)

        zapis.track_type = SciezkaPraktyki(form.track_type.data)
        db.session.commit()

        if form.track_type.data == 'STANDARD':
            return redirect(url_for('praktyki.kreator_firma', zapis_id=zapis.id))
        else:
            return redirect(url_for('praktyki.kreator_wniosek', zapis_id=zapis.id))

    if istniejacy and request.method == 'GET':
        form.track_type.data = istniejacy.track_type.value if istniejacy.track_type else 'STANDARD'

    return render_template('kreator/krok1_sciezka.html', form=form, praktyka=praktyka, istniejacy=istniejacy)


@praktyki_bp.route('/zgloszenie/<uuid:zapis_id>/kreator/firma', methods=['GET', 'POST'])
@login_required
def kreator_firma(zapis_id):
    """Krok 2A: Dane zakładu + ZOPZ (ścieżka A)."""
    zapis = db.session.get(ZapisPraktyki, zapis_id)
    if not zapis or zapis.student_id != current_user.id or zapis.track_type != SciezkaPraktyki.STANDARD:
        abort(404)

    form = FormularzDaneFirmy()
    firmy_list = db.session.query(Firma).filter_by(aktywna=True).order_by(Firma.nazwa).all()
    form.firma_id.choices = [('', '--- Wybierz firmę ---')] + [(str(f.id), f.nazwa) for f in firmy_list]
    uopz_list = db.session.query(Uzytkownik).filter_by(rola=RolaUzytkownika.UOPZ, aktywny=True).order_by(Uzytkownik.nazwisko).all()
    form.uopz_id.choices = [('', '--- Wybierz ---')] + [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]

    if form.validate_on_submit():
        if not form.ubezpieczenie_nw.data:
            flash('Ubezpieczenie NW jest wymagane.', 'danger')
            return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)

        zapis.termin_od  = form.termin_od.data
        zapis.termin_do  = form.termin_do.data
        zapis.uopz_id    = form.uopz_id.data if form.uopz_id.data else None
        zapis.ubezpieczenie_nw = True
        zapis.specjalnosc = getattr(current_user, 'specjalnosc', '') or ''

        if form.firma_typ.data == 'database':
            if not form.firma_id.data:
                flash('Wybierz firmę z listy.', 'danger')
                return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)
            zapis.firma_id = form.firma_id.data
            zapis.firma_nazwa = zapis.firma_adres = zapis.firma_miasto = None
            zapis.firma_nip_krs = zapis.firma_upowazniony_osoba = zapis.firma_upowazniony_stanowisko = None
        else:
            if not form.firma_nazwa.data or not form.firma_adres.data or not form.firma_miasto.data:
                flash('Podaj nazwę, adres i miasto firmy.', 'danger')
                return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)
            zapis.firma_id = None
            zapis.firma_nazwa                  = form.firma_nazwa.data
            zapis.firma_adres                  = form.firma_adres.data
            zapis.firma_miasto                 = form.firma_miasto.data
            zapis.firma_nip_krs                = form.firma_nip_krs.data
            zapis.firma_upowazniony_osoba      = form.firma_upowazniony_osoba.data
            zapis.firma_upowazniony_stanowisko = form.firma_upowazniony_stanowisko.data

        if not form.zopz_imie_nazwisko.data or not form.zopz_email.data:
            flash('Podaj imię/nazwisko i email opiekuna zakładowego (ZOPZ).', 'danger')
            return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)

        zapis.zopz_imie_nazwisko = form.zopz_imie_nazwisko.data
        zapis.zopz_stanowisko    = form.zopz_stanowisko.data
        zapis.zopz_telefon       = form.zopz_telefon.data
        zapis.zopz_email         = form.zopz_email.data
        db.session.commit()
        if zapis.status == StatusZapisu.AWAITING_APPROVAL:
            zapis.komentarze_uopz = None
            zapis.status = StatusZapisu.COMMISSION_REVIEW
            db.session.commit()
            flash('Dane zaktualizowane i zgłoszenie odesłane do komisji.', 'success')
            return redirect(url_for('praktyki.szczegoly_zgloszenia', id=zapis.id))
        return redirect(url_for('praktyki.zapisz_krok2', id=zapis.id))

    if request.method == 'GET':
        form.termin_od.data = zapis.termin_od
        form.termin_do.data = zapis.termin_do
        form.uopz_id.data   = str(zapis.uopz_id) if zapis.uopz_id else ''
        form.ubezpieczenie_nw.data = zapis.ubezpieczenie_nw
        form.firma_typ.data = 'database' if zapis.firma_id else 'custom'
        form.firma_id.data  = str(zapis.firma_id) if zapis.firma_id else ''
        form.firma_nazwa.data = zapis.firma_nazwa
        form.firma_adres.data = zapis.firma_adres
        form.firma_miasto.data = zapis.firma_miasto
        form.firma_nip_krs.data = zapis.firma_nip_krs
        form.firma_upowazniony_osoba.data = zapis.firma_upowazniony_osoba
        form.firma_upowazniony_stanowisko.data = zapis.firma_upowazniony_stanowisko
        form.zopz_imie_nazwisko.data = zapis.zopz_imie_nazwisko
        form.zopz_stanowisko.data = zapis.zopz_stanowisko
        form.zopz_telefon.data = zapis.zopz_telefon
        form.zopz_email.data = zapis.zopz_email

    return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)


@praktyki_bp.route('/zgloszenie/<uuid:zapis_id>/kreator/wniosek', methods=['GET', 'POST'])
@login_required
def kreator_wniosek(zapis_id):
    """Krok 2B/C: Wniosek dla ścieżek B i C."""
    zapis = db.session.get(ZapisPraktyki, zapis_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.track_type == SciezkaPraktyki.STANDARD:
        return redirect(url_for('praktyki.kreator_firma', zapis_id=zapis_id))

    form = FormularzWniosek()

    if form.validate_on_submit():
        zapis.firma_nazwa  = form.pracodawca_nazwa.data
        zapis.firma_adres  = form.pracodawca_adres.data
        zapis.firma_miasto = form.pracodawca_miasto.data
        zapis.zopz_stanowisko = form.stanowisko.data
        zapis.uzasadnienie_sciezki = form.uzasadnienie.data
        byl_awaiting = zapis.status == StatusZapisu.AWAITING_APPROVAL
        zapis.status = StatusZapisu.COMMISSION_REVIEW
        if byl_awaiting:
            zapis.komentarze_uopz = None
        db.session.commit()
        flash('Dane zaktualizowane i wniosek odesłany do komisji.' if byl_awaiting else 'Wniosek złożony. Oczekujesz na decyzję komisji.', 'success')
        return redirect(url_for('praktyki.szczegoly_zgloszenia', id=zapis.id))

    if request.method == 'GET':
        form.pracodawca_nazwa.data  = zapis.firma_nazwa
        form.pracodawca_adres.data  = zapis.firma_adres
        form.pracodawca_miasto.data = zapis.firma_miasto
        form.stanowisko.data        = zapis.zopz_stanowisko
        form.uzasadnienie.data      = zapis.uzasadnienie_sciezki

    return render_template('kreator/krok2bc_wniosek.html', form=form, zapis=zapis)




@praktyki_bp.route('/')
@login_required
def lista():
    dostepne = db.session.query(Praktyka)\
                 .filter_by(status=StatusPraktyki.ACTIVE)\
                 .order_by(Praktyka.rok_uczelniany.desc())\
                 .all()

    zapisy_data = {
        str(z.praktyka_id): {
            'id': str(z.id),
            'status': z.status.value,
            'sciezka': z.sciezka.value if z.sciezka else None,
            'wymaga_uwagi': (
                z.status == StatusZapisu.AWAITING_APPROVAL
                and bool(z.komentarze_uopz)
            ),
        }
        for z in db.session.query(ZapisPraktyki)\
                   .filter_by(student_id=current_user.id).all()
    }

    csrf_form = FlaskForm()
    return render_template('praktyki/lista.html', dostepne=dostepne, zapisy_data=zapisy_data, csrf_form=csrf_form)


@praktyki_bp.route('/zgloszenie/<uuid:id>/zakoncz', methods=['POST'])
@login_required
def zakoncz_praktyke(id):
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status != StatusZapisu.IN_PROGRESS:
        flash('Praktykę można zakończyć tylko gdy jest w trakcie realizacji.', 'warning')
        return redirect(url_for('praktyki.lista'))
    zapis.status = StatusZapisu.COMPLETED
    db.session.commit()
    flash('Praktyka została oznaczona jako zakończona. Dokumenty końcowe są teraz dostępne w zakładce Moje Dokumenty.', 'success')
    return redirect(url_for('praktyki.lista'))


@praktyki_bp.route('/<uuid:id>/zapisz/krok1')
@login_required
def zapisz_krok1(id):
    """Stara trasa — przekierowanie do nowego kreatora."""
    return redirect(url_for('praktyki.kreator_sciezka', id=id))



@praktyki_bp.route('/zgloszenie/<uuid:id>/krok2', methods=['GET', 'POST'])
@login_required
def zapisz_krok2(id):
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
        
    efekty = db.session.query(EfektUczenia).order_by(EfektUczenia.id).all()
        
    if request.method == 'POST':
        # Czyszczenie starego jeśli student wraca z jakiegoś powodu
        db.session.query(HarmonogramPraktyki).filter_by(zapis_id=zapis.id).delete()
        
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
        
        flash('Harmonogram zapisany.', 'success')
        return redirect(url_for('praktyki.szczegoly_zgloszenia', id=zapis.id))
    else:
        # GET request - pobranie istniejących danych harmonogramu
        istniejace_harmonogramy = {}
        harmonogramy = db.session.query(HarmonogramPraktyki).filter_by(zapis_id=zapis.id).all()
        for h in harmonogramy:
            istniejace_harmonogramy[str(h.learning_outcome_id)] = {
                'dzial': h.nazwa_dzialu,
                'prace': h.przykladowe_prace,
                'dni': h.liczba_dni
            }

    csrf_form = FlaskForm()

    return render_template('kreator/krok3_harmonogram.html',
                         zapis=zapis,
                         efekty=efekty,
                         csrf_form=csrf_form,
                         istniejace_harmonogramy=istniejace_harmonogramy)


@praktyki_bp.route('/zgloszenie/<uuid:id>/szczegoly')
@login_required
def szczegoly_zgloszenia(id):
    """Szczegóły zgłoszenia studenta wraz z komentarzami UOPZ"""
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    rows = (
        db.session.query(DokumentPrzeslany)
        .filter_by(zapis_id=id)
        .order_by(DokumentPrzeslany.przeslano_o.desc())
        .all()
    )
    uploaded_docs = [
        {
            'id': str(d.id),
            'original_filename': d.oryginalna_nazwa,
            'document_type': d.typ_dokumentu,
            'uploaded_at': d.przeslano_o,
        }
        for d in rows
    ]

    return render_template('praktyki/szczegoly_zgloszenia.html', zapis=zapis, uploaded_docs=uploaded_docs)


@praktyki_bp.route('/zgloszenie/<uuid:id>/resubmit', methods=['POST'])
@login_required
def resubmit_zgloszenia(id):
    """Student ponownie wysyła zgłoszenie po poprawkach."""
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status != StatusZapisu.AWAITING_APPROVAL:
        flash('Zgłoszenie nie może być ponownie wysłane w tym statusie.', 'warning')
        return redirect(url_for('praktyki.szczegoly_zgloszenia', id=id))
    zapis.status = StatusZapisu.COMMISSION_REVIEW
    zapis.komentarze_uopz = None
    db.session.commit()
    flash('Zgłoszenie zostało ponownie wysłane do weryfikacji komisji.', 'success')
    return redirect(url_for('praktyki.szczegoly_zgloszenia', id=id))


