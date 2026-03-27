"""
app_student/routes/dokumenty.py
Panel dokumentów do wydrukowania dla studenta
"""
import uuid
import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, make_response
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from app_student.extensions import db
from app_student.models import (ZapisPraktyki, StatusZapisu, Firma, IndywidualnyProgram,
                                StatusDokumentu, NumerPisma, HarmonogramPraktyki)
import httpx

dokumenty_bp = Blueprint('dokumenty', __name__)


def get_next_document_number():
    """Generuje kolejny numer pisma wychodzącego"""
    current_year = datetime.datetime.now().year

    # Znajdź ostatni numer w tym roku
    last_number = db.session.query(NumerPisma)\
        .filter(NumerPisma.numer.like(f'ANS/PZ/{current_year}/%'))\
        .order_by(NumerPisma.numer.desc())\
        .first()

    if last_number:
        # Wyciągnij numer i zwiększ o 1
        parts = last_number.numer.split('/')
        last_num = int(parts[-1])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"ANS/PZ/{current_year}/{next_num:03d}"


@dokumenty_bp.route('/')
@login_required
def panel_dokumentow():
    """Panel wszystkich dokumentów studenta"""

    # Pobierz wszystkie zapisy praktyk studenta
    zapisy = db.session.query(ZapisPraktyki)\
        .filter_by(student_id=current_user.id)\
        .order_by(ZapisPraktyki.enrolled_at.desc())\
        .all()

    dokumenty_data = []

    for zapis in zapisy:
        # Sprawdź czy harmonogram został wypełniony
        harmonogram_count = db.session.query(HarmonogramPraktyki)\
            .filter_by(enrollment_id=zapis.id)\
            .count()

        # Sprawdź czy firma ma stałą umowę
        firma_ma_umowe = False
        if zapis.firma:
            firma_ma_umowe = zapis.firma.has_standing_agreement

        # Sprawdź status indywidualnego programu
        program = db.session.query(IndywidualnyProgram)\
            .filter_by(enrollment_id=zapis.id)\
            .first()

        program_approved = program and program.approved_by_uopz if program else False

        dokumenty_data.append({
            'zapis': zapis,
            'harmonogram_gotowy': harmonogram_count > 0,
            'firma_ma_umowe': firma_ma_umowe,
            'program_approved': program_approved,
            'mozna_generowac': (
                zapis.status in [StatusZapisu.AWAITING_APPROVAL, StatusZapisu.IN_PROGRESS]
                and harmonogram_count > 0
            )
        })

    csrf_form = FlaskForm()
    return render_template('dokumenty/panel.html',
                         dokumenty_data=dokumenty_data,
                         csrf_form=csrf_form)


@dokumenty_bp.route('/generuj/<uuid:enrollment_id>/<doc_type>')
@login_required
def generuj_dokument(enrollment_id, doc_type):
    """Generuje konkretny dokument PDF"""

    zapis = db.session.get(ZapisPraktyki, enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    # Sprawdź czy można generować dokumenty
    if zapis.status not in [StatusZapisu.AWAITING_APPROVAL, StatusZapisu.IN_PROGRESS]:
        flash('Dokumenty można generować tylko dla zatwierdzonych praktyk.', 'error')
        return redirect(url_for('dokumenty.panel_dokumentow'))

    # Sprawdź czy harmonogram jest wypełniony
    harmonogram_count = db.session.query(HarmonogramPraktyki)\
        .filter_by(enrollment_id=zapis.id)\
        .count()

    if harmonogram_count == 0:
        flash('Najpierw uzupełnij harmonogram praktyki.', 'error')
        return redirect(url_for('praktyki.zapisz_krok2', id=zapis.id))

    # Dla załącznika 3 sprawdź czy firma nie ma stałej umowy
    if doc_type == 'ZALACZNIK_3':
        if zapis.firma and zapis.firma.has_standing_agreement:
            flash('Załącznik 3 nie jest wymagany - firma ma stałą umowę z uczelnią.', 'error')
            return redirect(url_for('dokumenty.panel_dokumentow'))

    # Dla załącznika 4 sprawdź zatwierdzenie UOPZ
    if doc_type == 'ZALACZNIK_4':
        program = db.session.query(IndywidualnyProgram)\
            .filter_by(enrollment_id=zapis.id)\
            .first()

        if not program or not program.approved_by_uopz:
            flash('Indywidualny Program Praktyk musi być zatwierdzony przez UOPZ.', 'error')
            return redirect(url_for('dokumenty.panel_dokumentow'))

    # Generuj numer pisma dla załącznika 2
    numer_pisma = None
    if doc_type == 'ZALACZNIK_2':
        existing_number = db.session.query(NumerPisma)\
            .filter_by(enrollment_id=zapis.id, document_type='ZALACZNIK_2')\
            .first()

        if not existing_number:
            numer_pisma = get_next_document_number()
            new_number = NumerPisma(
                id=uuid.uuid4(),
                enrollment_id=zapis.id,
                document_type='ZALACZNIK_2',
                numer=numer_pisma
            )
            db.session.add(new_number)
            db.session.commit()
        else:
            numer_pisma = existing_number.numer

    # Przygotuj dane do generacji PDF
    data = {
        'student': {
            'imie': zapis.student.first_name,
            'nazwisko': zapis.student.last_name,
            'nr_albumu': zapis.student.album_number,
        },
        'praktyka': {
            'rok_uczelniany': zapis.praktyka.rok_uczelniany,
            'semestr': zapis.praktyka.semestr,
            'wymiar_godzin': zapis.praktyka.wymiar_godzin
        },
        'firma': {
            'nazwa': zapis.firma_nazwa,
            'adres': zapis.firma_adres,
            'miasto': zapis.firma_miasto,
            'nip_krs': zapis.firma_nip_krs
        },
        'terminy': {
            'od': zapis.termin_od.strftime('%d.%m.%Y') if zapis.termin_od else '',
            'do': zapis.termin_do.strftime('%d.%m.%Y') if zapis.termin_do else ''
        },
        'numer_pisma': numer_pisma,
        'zopz': {
            'imie_nazwisko': zapis.zopz_imie_nazwisko,
            'stanowisko': zapis.zopz_stanowisko,
            'telefon': zapis.zopz_telefon,
            'email': zapis.zopz_email
        }
    }

    # Dodaj harmonogram dla załącznika 4
    if doc_type == 'ZALACZNIK_4':
        harmonogram = db.session.query(HarmonogramPraktyki)\
            .filter_by(enrollment_id=zapis.id)\
            .all()

        data['harmonogram'] = [{
            'efekt_kod': h.efekt.kod,
            'efekt_opis': h.efekt.opis,
            'dzial': h.nazwa_dzialu,
            'prace': h.przykladowe_prace,
            'dni': h.liczba_dni
        } for h in harmonogram]

    try:
        # Wywołaj tex-service
        response = httpx.post(
            'http://tex-service:5002/compile',
            json={
                'template': f'{doc_type.lower()}.tex.j2',
                'data': data
            },
            timeout=30
        )

        if response.status_code == 200:
            pdf_response = make_response(response.content)
            pdf_response.headers['Content-Type'] = 'application/pdf'
            pdf_response.headers['Content-Disposition'] = f'attachment; filename="{doc_type}_{zapis.student.last_name}.pdf"'
            return pdf_response
        else:
            flash(f'Błąd generowania dokumentu: {response.text}', 'error')

    except Exception as e:
        flash(f'Błąd połączenia z serwisem PDF: {str(e)}', 'error')

    return redirect(url_for('dokumenty.panel_dokumentow'))


@dokumenty_bp.route('/zatwierdz-program/<uuid:enrollment_id>', methods=['POST'])
@login_required
def zatwierdz_program(enrollment_id):
    """Student prosi o zatwierdzenie indywidualnego programu"""

    zapis = db.session.get(ZapisPraktyki, enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    # Sprawdź czy harmonogram jest wypełniony
    harmonogram_count = db.session.query(HarmonogramPraktyki)\
        .filter_by(enrollment_id=zapis.id)\
        .count()

    if harmonogram_count == 0:
        flash('Najpierw uzupełnij harmonogram praktyki.', 'error')
        return redirect(url_for('praktyki.zapisz_krok2', id=zapis.id))

    # Stwórz lub zaktualizuj wpis programu
    program = db.session.query(IndywidualnyProgram)\
        .filter_by(enrollment_id=zapis.id)\
        .first()

    if not program:
        program = IndywidualnyProgram(
            id=uuid.uuid4(),
            enrollment_id=zapis.id,
            status=StatusDokumentu.AWAITING_APPROVAL
        )
        db.session.add(program)
    else:
        program.status = StatusDokumentu.AWAITING_APPROVAL
        program.approved_by_uopz = False
        program.approved_at = None

    db.session.commit()

    flash('Prośba o zatwierdzenie Indywidualnego Programu została wysłana do UOPZ.', 'success')
    return redirect(url_for('dokumenty.panel_dokumentow'))