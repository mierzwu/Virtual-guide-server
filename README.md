================================================================================
                    DOKUMENTACJA PROJEKTU: VIRTUAL GUIDE SERVER
================================================================================

1. OPIS OGOLNY
================================================================================

Virtual Guide Server to serwer REST API napisany w Pythonie (Flask), ktory
sluzy jako backend dla aplikacji mobilnej "wirtualny przewodnik". Uzytkownik
wysyla zdjecie obiektu (budynku, zabytku, pomnika itp.) wraz z opcjonalnymi
wspolrzednymi GPS, a serwer identyfikuje obiekt i zwraca informacje z Wikipedii.

Stos technologiczny:
  - Python 3 + Flask
  - SQLAlchemy + SQLite (baza danych historii)
  - Google Cloud Vision API (rozpoznawanie obiektow i etykiet)
  - Wikipedia API (polskojezyczna i anglojezyczna)


2. STRUKTURA PROJEKTU
================================================================================

  config.py          - Konfiguracja aplikacji (klucze API, baza danych, limity)
  run.py             - Punkt wejscia serwera (uruchamia Flask na porcie 5000)
  init_db.py         - Inicjalizacja tabel w bazie danych
  requirements.txt   - Zależności Pythona
  app/
    __init__.py      - Fabryka aplikacji Flask (create_app)
    extensions.py    - Instancja SQLAlchemy
    models.py        - Model bazy danych (tabela History)
    routes.py        - Endpointy API (/health, /guide, /history)
    vision.py        - Integracja z Google Vision API
    wiki.py          - Integracja z Wikipedia API + SYSTEM PUNKTACJI
  uploads/           - Folder na przesylane zdjecia


3. ENDPOINTY API
================================================================================

Wszystkie endpointy (poza /health) wymagaja naglowka:
  X-API-Key: <klucz z .env>

3.1  GET /health
    Zwraca: {"status": "ok"}
    Opis: Sprawdzenie czy serwer dziala.

3.2  POST /guide
    Parametry (multipart/form-data):
      - image (wymagany)  — plik graficzny (png, jpg, jpeg, webp), max 16 MB
      - latitude (opcja)  — szerokosc geograficzna (np. "52.2297")
      - longitude (opcja) — dlugosc geograficzna (np. "21.0122")

    Przeplyw:
      1. Kompresja obrazu do max 4 MB (jesli potrzeba)
      2. Wyslanie do Google Vision API (Landmark Detection + Label Detection)
      3a. Jesli Vision wykryl landmark:
          → Pobranie info z Wikipedii dla najlepszego wyniku
          → Jesli GPS podane: sortowanie landmarkow wg odleglosci
          → Ostrzezenie jesli odleglosc > 300m
      3b. Jesli Vision NIE wykryl landmarka (fallback etykietowy):
          → Uruchomienie SYSTEMU PUNKTACJI (search_by_labels)
          → Dopasowanie artykulu Wikipedii na podstawie etykiet + GPS

    Odpowiedz: JSON z polami message, id, landmarks, labels, wiki, nearby,
               debug_log (logi diagnostyczne)

3.3  GET /history
    Zwraca: Lista wszystkich wczesniejszych zapytan (najnowsze pierwsze).
    Pola: id, file_path, latitude, longitude, created_at, ai_title,
          ai_description, ai_links


4. GOOGLE VISION API
================================================================================

Serwer wysyla obraz do Google Cloud Vision API z dwoma typami detekcji:

  - LANDMARK_DETECTION (max 50 wynikow)
    Rozpoznaje znane obiekty architektoniczne. Zwraca nazwe, pewnosc (score)
    i wspolrzedne GPS landmarka.

  - LABEL_DETECTION (max 20 wynikow)
    Zwraca etykiety opisujace zawartosc obrazu (np. "Church", "Building",
    "Gothic architecture") wraz z pewnoscia (score 0.0–1.0).

Obraz jest kompresowany przed wyslaniem — najpierw obnizajac jakosc JPEG
(od 85 do 30), potem zmniejszajac wymiary (75% przy kazdej iteracji).

W przypadku bledu polaczenia, serwer ponawia probe do 3 razy z wykladniczym
opoznieniem (2^attempt sekund).


5. SYSTEM PUNKTACJI (SCORING) — SZCZEGOLOWY OPIS
================================================================================

System punktacji jest kluczowym elementem serwera. Uruchamia sie, gdy Google
Vision API NIE rozpozna bezposrednio landmarka na zdjeciu, ale zwroci
etykiety opisowe. System laczy te etykiety z danymi GPS, aby znalezc
najbardziej prawdopodobny obiekt w poblizu uzytkownika.

Caly proces realizuje funkcja search_by_labels() w pliku app/wiki.py.


5.1  ETAP 1 — FILTROWANIE ETYKIET
--------------------------------------------------------------------------------

Etykiety z Vision API sa filtrowane przez funkcje filter_labels():

  a) Usuwane sa etykiety z CZARNEJ LISTY (BLACKLISTED_KEYWORDS):
     Kategorie niezwiazane z architektura: rosliny, jedzenie, zwierzeta, osoby,
     pojazdy, ubrania, meble, elektronika, niebo/natura, sztuka, tekst, wnetrza.
     Przyklad: "plant", "food", "car", "person", "sky", "furniture"

  b) Zachowane sa TYLKO etykiety pasujace do BIALEJ LISTY (LANDMARK_KEYWORDS):
     Kategorie zwiazane z architektura i zabytkami.
     Przyklad: "building", "church", "cathedral", "castle", "tower", "bridge",
              "monument", "museum", "gothic", "baroque", "renaissance"

  Filtrowanie uzywa dopasowania na poziomie slow (word-level matching):
    - Slowa jednoczlonowe musza byc dokladnym slowem (np. "cat" nie pasuje do
      "cathedral").
    - Frazy wielowyrazowe sa dopasowywane jako podciag.


5.2  ETAP 2 — BUDOWANIE ETYKIET DO PUNKTACJI
--------------------------------------------------------------------------------

Do punktacji uzywane sa dwa typy etykiet:

  - ETYKIETY PIERWSZORZEDNE (primary labels):
    Te, ktore przeszly filtr z Etapu 1. Maja pelna wage.

  - ETYKIETY DRUGORZENDY / "MIEKKIE" (soft labels):
    Wszystkie pozostale etykiety z Vision API (te, ktore NIE przeszly filtru).
    Ich waga (score) jest ZREDUKOWANA do 15% oryginalnej wartosci.
    Dzieki temu moga wciaz pomoc w dopasowaniu, ale nie dominuja punktacji.


5.3  ETAP 3 — WYSZUKIWANIE ARTYKULOW WIKIPEDIA (GEOSEARCH)
--------------------------------------------------------------------------------

Serwer szuka artykulow Wikipedii w promieniu 300 metrow od wspolrzednych GPS
uzytkownika (max 20 artykulow). Probuje najpierw polska Wikipedie, potem
angielska.

Dla kazdego znalezionego artykulu pobierane sa:
  - Tytul strony
  - Kategorie (do filtrowania i dopasowywania)
  - Fragment tekstu (extract, do 5000 znakow)


5.4  ETAP 4 — FILTROWANIE ARTYKULOW
--------------------------------------------------------------------------------

Artykuly sa filtrowane, aby odrzucic te niezwiazane z fizycznymi obiektami:

  ODRZUCANE (WIKI_SKIP_KEYWORDS):
    Parafie, diecezje, dekanaty, gminy, powiaty, wojewodztwa, osoby (urodzeni/
    zmarli), biskupi, duchowni, organizacje, stowarzyszenia, partie polityczne.

  ZACHOWANE (WIKI_BUILDING_KEYWORDS):
    Koscioly, bazyliki, katedry, zamki, palace, pomniki, mosty, wieze, muzea,
    budynki, zabytki, fortyfikacje, bramy, ratusze, dworce, synagogi, meczety,
    klasztory, opactwa, kaplice, stadiony, fontanny, latarnie, wiatraki,
    amfiteatry, atrakcje.

  Logika: artykul jest ODRZUCANY tylko jesli pasuje do SKIP i NIE pasuje
  do BUILDING.


5.5  ETAP 5 — OBLICZANIE WAG IDF (Inverse Document Frequency)
--------------------------------------------------------------------------------

Przed punktacja obliczane sa wagi IDF dla kazdej etykiety:

  Cel: Etykiety, ktore pasuja do MNIEJSZEJ liczby artykulow, sa wartosc-
  ciowsze (bardziej unikalne) i dostaja wyzsza wage.

  Wzor:
    IDF(etykieta) = log(N / ilosc_artykulow_z_ta_etykieta) + 1.0

  Gdzie N = calkowita liczba artykulow po filtracji.

  Przyklady:
    - Etykieta "Building" wystepuje w 8 z 10 artykulow → IDF = log(10/8)+1 ≈ 1.22
    - Etykieta "Gothic" wystepuje w 1 z 10 artykulow → IDF = log(10/1)+1 ≈ 3.30
    - Etykieta niewystepujaca w zadnym artykule → IDF = 1.0 (neutralna)

  Efekt: Unikalne etykiety (np. "Gothic", "Baroque") daja wiecej punktow
  niz popularne (np. "Building").


5.6  ETAP 6 — PUNKTACJA ARTYKULU (funkcja _score_article)
--------------------------------------------------------------------------------

Kazdy artykul jest oceniany wzgledem etykiet. Dla KAZDEJ etykiety obliczane sa
punkty podle nastepujacego algorytmu:

  DANE WEJSCIOWE:
    - base = vision_score etykiety (0.0 – 1.0)
      (dla soft labels: base = oryginalny_score * 0.15)
    - desc = opis etykiety po angielsku (np. "church")
    - pl = tlumaczenie polskie (np. "kosciol") — ze slownika LABEL_TRANSLATIONS

  1) WYSZUKIWANIE W TYTULE ARTYKULU:
     Sprawdza, czy etykieta (angielska LUB polska) wystepuje w tytule.
     → in_title = True/False

  2) WYSZUKIWANIE W TRESCI ARTYKULU:
     Szuka pierwszego wystapienia etykiety (angielskiej i polskiej) w tekscie
     artykulu (kategorie + extract).
     → Zapisuje pozycję (pos) najwczesniejszego trafienia.

  3) OBLICZANIE BONUSU POZYCYJNEGO:
     Im wczesniej etykieta wystapila w tekscie, tym wiecej punktow:

       position_bonus = (1.0 - pos / dlugosc_tekstu) * base

     Przyklad (base = 0.9, tekst ma 5000 znakow):
       - Etykieta na poz. 0      → bonus = (1.0 - 0/5000) * 0.9     = 0.900
       - Etykieta na poz. 500    → bonus = (1.0 - 500/5000) * 0.9   = 0.810
       - Etykieta na poz. 4500   → bonus = (1.0 - 4500/5000) * 0.9  = 0.090
       - Tylko w tytule (brak w tekście) → bonus = base              = 0.900

  4) SUMA PUNKTOW DLA ETYKIETY:
       points = base + position_bonus

     Przyklad (base=0.9, etykieta na poz. 500):
       points = 0.9 + 0.810 = 1.710

  5) MNOZNIK ZA TRAFIENIE W TYTUL (×3.0):
     Jesli etykieta wystapila w tytule artykulu:
       points = points * 3.0

     Przyklad: 1.710 * 3.0 = 5.130

  6) MNOZNIK IDF:
       points = points * IDF(etykieta)

     Przyklad (IDF = 2.5):
       5.130 * 2.5 = 12.825

  7) WYNIK KONCOWY DLA ETYKIETY:
     Punkty za te etykiete sa dodawane do lacznego wyniku artykulu (label_score).


  PODSUMOWANIE WZORU DLA JEDNEJ ETYKIETY:

    points = (base + position_bonus) * [3.0 jesli in_title, 1.0 wpp] * IDF

    Gdzie:
      base           = vision_score (0.0–1.0, dla soft: *0.15)
      position_bonus = (1.0 - pos/len_text) * base   [jesli znaleziono w tekscie]
                     = base                           [jesli tylko w tytule]
      Warunek: etykieta musi byc znaleziona w tytule LUB w tresci artykulu.
               Jesli nie znaleziono — 0 punktow.


5.7  ETAP 7 — MNOZNIK ODLEGLOSCI (Distance Multiplier)
--------------------------------------------------------------------------------

Po obliczeniu label_score, wynik jest modyfikowany przez mnoznik odleglosci.
Jest to wykladniczy spadek premiujacy bliskosc do uzytkownika.

  Wzor:
    distance_multiplier = 1.0 + 5.0 * exp(-dist / 80)

  Gdzie dist = odleglosc w metrach miedzy uzytkownikiem a artykulem Wikipedia.

  Wartosci mnoznika:
    Odleglosc     Mnoznik
    ─────────     ───────
       0 m        ×6.00     (maksymalna premia za bycie "na miejscu")
      20 m        ×4.89
      50 m        ×3.68
      63 m        ×3.27
      80 m        ×2.84
     100 m        ×2.43
     150 m        ×1.77
     200 m        ×1.41
     244 m        ×1.24
     300 m        ×1.12
     500 m        ×1.01     (praktycznie brak premii)

  Efekt: Obiekt stojacy 0m od uzytkownika dostaje 6x wiecej punktow niz
  obiekt w odleglosci 500m. Spadek jest gwaltowny — roznica miedzy 0m a
  100m jest ogromna (6.0 vs 2.4).


5.8  ETAP 8 — BAZOWY PUNKT OBECNOSCI (Presence Score)
--------------------------------------------------------------------------------

Kazdy artykul (budynek/zabytek) dostaje staly bazowy punkt:

  presence_score = 1.0

  Cel: Gdy zadna etykieta nie pasuje do zadnego artykulu (label_score = 0
  dla wszystkich), sam mnoznik odleglosci decyduje o zwyciezcy.
  Najbliższy budynek wygrywa dzieki najwyzszemu distance_multiplier
  pomnozonemu przez presence_score.


5.9  ETAP 9 — WYNIK KONCOWY ARTYKULU
--------------------------------------------------------------------------------

  final_score = (label_score + presence_score) * distance_multiplier

  Przyklad 1 — Kosciol 50m od uzytkownika, label_score = 8.5:
    final_score = (8.5 + 1.0) * 3.68 = 34.94

  Przyklad 2 — Zamek 200m od uzytkownika, label_score = 12.0:
    final_score = (12.0 + 1.0) * 1.41 = 18.33

  Przyklad 3 — Budynek 10m, brak dopasowanych etykiet:
    final_score = (0.0 + 1.0) * 5.43 = 5.43

  Wniosek: Bliski kosciol z Przykladu 1 wygrywa z odleglym zamkiem
  z Przykladu 2, mimo ze zamek mial wyzszy label_score.


5.10  ETAP 10 — WYBOR ZWYCIEZCY I PEWNOSC (Confidence)
--------------------------------------------------------------------------------

Artykuly sa sortowane malejaco wg final_score. Najlepszy artykul wygrywa.

  Pewnosc (confidence) jest obliczana jako:

    confidence = min(best_score / (best_score + second_best_score), 1.0)

  Przyklady:
    best=35, second=5   → confidence = 35/40  = 0.875 (87.5%)
    best=35, second=30  → confidence = 35/65  = 0.538 (53.8%)
    best=35, brak drug. → confidence = 1.0    (100%)

  Interpretacja: Im wieksza roznica miedzy 1. a 2. wynikiem, tym wieksza
  pewnosc dopasowania.


5.11  SCHEMAT BLOKOWY SYSTEMU PUNKTACJI
--------------------------------------------------------------------------------

  Zdjecie + GPS
       |
       v
  [Google Vision API]
       |
       +---> Landmark Detection → znaleziono? → TAK → Wikipedia info → KONIEC
       |                                         |
       |                                        NIE
       v                                         |
  [Label Detection]                              v
       |                           [1. Filtrowanie etykiet]
       |                           (biala/czarna lista)
       |                                         |
       |                                         v
       |                           [2. Podział: primary + soft labels]
       |                                         |
       |                                         v
       |                           [3. Geosearch Wikipedia 300m]
       |                                         |
       |                                         v
       |                           [4. Filtrowanie artykulow]
       |                           (budynki/zabytki vs parafie/gminy)
       |                                         |
       |                                         v
       |                           [5. IDF — wagi unikalnosci etykiet]
       |                                         |
       |                                         v
       |                           [6. Punktacja: base + position + title + IDF]
       |                                         |
       |                                         v
       |                           [7. Mnoznik odleglosci (exp decay)]
       |                                         |
       |                                         v
       |                           [8. + Presence score (1.0)]
       |                                         |
       |                                         v
       |                           [9. final_score = (label+1) * dist_mult]
       |                                         |
       |                                         v
       |                           [10. Sortowanie → zwyciezca + confidence]
       |                                         |
       |                                         v
       +---------------------------------> [Wikipedia info] → ODPOWIEDZ


6. INTEGRACJA Z WIKIPEDIA
================================================================================

Serwer korzysta z dwoch API Wikipedii:

  a) REST API (rest_v1/page/summary):
     Pobiera opis, miniaturke, pelnorozmiarowy obraz i URL strony.

  b) Action API (w/api.php):
     - Geosearch: szukanie artykulow w promieniu od wspolrzednych GPS
     - Extracts: pobieranie dluzszych fragmentow tekstu (do 5000 zn.)
     - Categories: pobieranie kategorii artykulu
     - Images: pobieranie zdjec ze strony
     - Pageimages: pobieranie miniaturek
     - Search: wyszukiwanie pelnotekstowe (fallback gdy brak bezposredniej strony)

  Kolejnosc jezykowa: zawsze najpierw polska Wikipedia, potem angielska.

  Tlumaczenia etykiet: Slownik LABEL_TRANSLATIONS (ponad 70 par EN→PL)
  umozliwia dopasowywanie angielskich etykiet Vision API do polskich artykulow
  Wikipedii.


7. BAZA DANYCH
================================================================================

SQLite z jedna tabela:

  Tabela: history
    id             INTEGER PRIMARY KEY AUTOINCREMENT
    file_path      VARCHAR(255) NOT NULL — sciezka do zapisanego zdjecia
    latitude       NUMERIC(10,7)        — szerokosc geograficzna
    longitude      NUMERIC(10,7)        — dlugosc geograficzna
    created_at     DATETIME NOT NULL     — czas utworzenia (domyslnie NOW)
    ai_title       VARCHAR(255)         — tytul rozpoznanego obiektu
    ai_description TEXT                  — opis z Wikipedii
    ai_links       JSON                 — URL do artykulu Wikipedii


8. KONFIGURACJA
================================================================================

Plik .env (wymagane zmienne):
  SECRET_KEY           — klucz API do autoryzacji zapytan
  GOOGLE_VISION_API_KEY — klucz Google Cloud Vision API
  UPLOAD_FOLDER        — folder na zdjecia (domyslnie: "uploads")

Limity:
  - Max rozmiar przesylanego pliku: 16 MB
  - Max rozmiar obrazu wysylanego do Vision: 4 MB (automatyczna kompresja)
  - Promien geosearch Wikipedia: 300 m
  - Max artykulow z geosearch: 20
  - Ostrzezenie o odleglosci landmarka: > 300 m


9. URUCHAMIANIE
================================================================================

  1. Zainstaluj zaleznosci:
       pip install -r requirements.txt

  2. Utworz plik .env z wymaganymi zmiennymi (patrz sekcja 8)

  3. Zainicjalizuj baze danych:
       python init_db.py

  4. Uruchom serwer:
       python run.py

  Serwer startuje na http://0.0.0.0:5000 w trybie debug.

================================================================================
         DOKUMENTACJA PROJEKTU "VIRTUAL GUIDE" — STRONA KLIENCKA
================================================================================

Wersja:         0.1.0
Pakiet:         com.mierzwu.virtualguide
Platforma:      Android (glowna) / Desktop (ograniczona funkcjonalnosc)
Framework UI:   Kivy 2.3.0
Jezyk:          Python 3.12


================================================================================
 1. OPIS OGOLNY
================================================================================

Virtual Guide to mobilna aplikacja-przewodnik, ktora pozwala uzytkownikowi
zrobic lub zaimportowac zdjecie obiektu (np. zabytku, budynku), a nastepnie
wyslac je do zdalnego serwera w celu analizy. Serwer rozpoznaje obiekt
(za pomoca Google Vision API), wzbogaca wynik danymi z Wikipedii i zwraca
opis, zdjecia, link do Wikipedii oraz liste pobliskich miejsc.

Aplikacja kliencka jest zbudowana w oparciu o framework Kivy i przeznaczona
glownie na Androida (budowana za pomoca Buildozer / python-for-android).
Na desktopie dziala w ograniczonym trybie — bez aparatu i GPS.


================================================================================
 2. STRUKTURA PLIKOW KLIENCKICH
================================================================================

  main.py          — Punkt wejscia aplikacji; klasa PhotoApp
  ui.py            — Mixin UIMixin: nawigacja ekranow, spinner, galeria, popup
  camera.py        — Mixin CameraMixin: obsluga aparatu na Android (MediaStore)
  gps.py           — Mixin GPSMixin: pobieranie wspolrzednych GPS
  permissions.py   — Mixin PermissionsMixin: obsluga uprawnien Android
  server.py        — Mixin ServerMixin: komunikacja z serwerem, parsowanie JSON
  env.py           — Ladowanie zmiennych z pliku .env
  photo_app.kv     — Layout UI w jezyku Kivy (KV Language)
  requirements.txt — Zaleznosci Pythonowe
  buildozer.spec   — Konfiguracja budowania APK


================================================================================
 3. ARCHITEKTURA — WZORZEC MIXIN
================================================================================

Glowna klasa PhotoApp dziedziczy po wielu mixinach i klasie App z Kivy:

    class PhotoApp(UIMixin, CameraMixin, GPSMixin, ServerMixin,
                   PermissionsMixin, App):

Kazdy mixin odpowiada za izolowany obszar funkcjonalnosci:

  +------------------+    +------------------+    +------------------+
  |    UIMixin       |    |  CameraMixin     |    |    GPSMixin      |
  | - spinner        |    | - capture_photo  |    | - _get_gps_      |
  | - nawigacja      |    | - MediaStore     |    |   payload()      |
  | - galeria        |    | - EXIF fix       |    | - LocationMgr    |
  | - file picker    |    | - content:// URI |    | - fresh fix      |
  | - dev settings   |    +------------------+    +------------------+
  +------------------+
                          +------------------+    +------------------+
                          |  ServerMixin     |    | PermissionsMixin |
                          | - send_photo     |    | - check perms    |
                          | - parse response |    | - request perms  |
                          | - download imgs  |    | - callbacks      |
                          +------------------+    +------------------+

Wszystkie mixiny operuja na wspolnych wlasciwosciach (Kivy Properties)
zdefiniowanych w PhotoApp.


================================================================================
 4. SZCZEGOLOWY OPIS MODULOW
================================================================================

────────────────────────────────────────────────────────────────────────────────
 4.1  main.py — Klasa PhotoApp
────────────────────────────────────────────────────────────────────────────────

Plik wejsciowy aplikacji. Definiuje klase PhotoApp z nastepujacymi
elementami:

STALE KONFIGURACYJNE:
  DEFAULT_SERVER_URL    — Domyslny URL serwera z pliku .env
  DEFAULT_API_KEY       — Domyslny klucz API z pliku .env

WLASCIWOSCI KIVY (StringProperty / BooleanProperty / ListProperty):
  image_path            — Sciezka do aktualnie wybranego/zrobionego zdjecia
  status_text           — Tekst statusu wyswietlany na ekranie importu
  guide_title           — Tytul rozpoznanego obiektu
  guide_text            — Opis obiektu (z Wikipedii)
  guide_confidence      — Poziom pewnosci rozpoznania (np. "95.3%")
  guide_warning         — Ostrzezenie od serwera
  guide_rest            — Dodatkowe informacje
  guide_message         — Wiadomosc (np. "nie rozpoznano zadnego obiektu")
  guide_message_labels  — Etykiety ostrzezen (wyswietlane na czerwono)
  guide_nearby          — Lista pobliskich obiektow (list of dict)
  guide_images          — Lista sciezek do pobranych zdjec
  guide_debug_log       — Pelny log debugowania z serwera
  wiki_url              — Link do artykulu Wikipedia
  response_image_path   — Sciezka do obrazu z odpowiedzi serwera
  server_url            — Aktualny URL serwera
  api_key               — Aktualny klucz API
  dev_latitude          — Reczna szerokosc geograficzna (tryb deweloperski)
  dev_longitude         — Reczna dlugosc geograficzna (tryb deweloperski)
  is_sending            — Flaga: czy trwa wysylanie (blokuje UI)

METODY:
  build()
    - Ustawia kolor tla okna (ciemny motyw: rgba 0.08, 0.10, 0.14)
    - Laduje ustawienia deweloperskie
    - Laduje layout z photo_app.kv
    - Binduje is_sending do sterowania spinnerem

  _settings_store() -> JsonStore
    - Zwraca obiekt JsonStore w katalogu user_data_dir
    - Plik: developer_settings.json

  _load_developer_settings()
    - Laduje server_url, api_key, dev_latitude, dev_longitude
    - Domyslne wartosci z .env, nadpisywane przez zapisane ustawienia

  _save_developer_settings()
    - Zapisuje biezace ustawienia do JsonStore


────────────────────────────────────────────────────────────────────────────────
 4.2  ui.py — UIMixin
────────────────────────────────────────────────────────────────────────────────

Mixin dostarczajacy funkcje interfejsu uzytkownika.

SPINNER (animacja ladowania):
  _toggle_spinner(instance, value)
    - Reaguje na zmiane is_sending — startuje/zatrzymuje animacje

  _start_spinner()
    - Uruchamia Clock.schedule_interval co 1/30s
    - Rysuje obracajacy sie luk (SmoothLine) na widgecie spinner_widget

  _stop_spinner()
    - Anuluje harmonogram, czysci canvas spinnera

  _spin_tick(dt)
    - Pojedynczy krok animacji: obraca luk o 6 stopni

NAWIGACJA EKRANOW:
  _get_screen_manager()
    - Zwraca ScreenManager z roota aplikacji

  _go_to_response_screen()
    - Przechodzi na ekran "response"

  back_to_import_screen()
    - Wraca na ekran "import"

  go_to_debug_log_screen()
    - Przechodzi na ekran "debug_log"

  back_to_response_screen()
    - Wraca z debug_log na "response"

  copy_debug_log()
    - Kopiuje zawartosc guide_debug_log do schowka systemowego

PODGLAD ZDJECIA:
  _show_image(path, status_text)
    - Waliduje sciezke (lokalna lub content://)
    - Ustawia preview i status_text

  _set_preview(path) [@mainthread]
    - Resetuje image_path i ustawia nowe zrodlo po jednej klatce
    - Wymusza przeladowanie widgetu image_preview

GALERIA ZDJEC:
  _populate_image_gallery() [@mainthread]
    - Czysci kontener galerii zdjec (GridLayout image_gallery)

  _add_gallery_image(local_path) [@mainthread]
    - Dodaje pobrany obraz do galerii
    - Rozmiar kazdego obrazu: 300x300 px
    - Aktualizuje szerokosc galerii i liste guide_images

POBLISKIE MIEJSCA:
  _populate_nearby() [@mainthread]
    - Tworzy karty pobliskich miejsc na podstawie guide_nearby
    - Kazda karta zawiera: miniature, tytul, przycisk Wikipedia
    - Karty sa BoxLayout (horizontal) z dynamiczna wysokoscia

  _update_nearby_image(index, local_path) [@mainthread]
    - Aktualizuje miniature w karcie pobliskiego miejsca (po pobraniu)

WIKI URL:
  open_wiki_url()
    - Otwiera wiki_url w przegladarce systemowej (webbrowser.open)

FILE PICKER:
  pick_photo()
    - Android: uzywa plyer.filechooser.open_file
    - Desktop: otwiera Kivy FileChooserListView w Popup
    - Obslugiwane formaty: jpg, jpeg, png, bmp, webp

  _open_kivy_file_picker()
    - Tworzy popup z FileChooserListView
    - Przyciski: "Anuluj" / "Wybierz"

USTAWIENIA DEWELOPERSKIE:
  open_developer_settings()
    - Otwiera popup z formularzem:
      * Adres serwera (TextInput)
      * API Key (TextInput, password=True)
      * Szerokosc geograficzna (TextInput)
      * Dlugosc geograficzna (TextInput)
    - Przycisk "Zapisz" wywoluje _save_developer_settings()
    - Tekst informacyjny: "Puste = automatycznie z GPS"


────────────────────────────────────────────────────────────────────────────────
 4.3  camera.py — CameraMixin
────────────────────────────────────────────────────────────────────────────────

Mixin obslugujacy robienie zdjec na Androidzie.

STAN WEWNETRZNY:
  _pending_camera_output_path   — Sciezka docelowa dla zdjecia
  _pending_media_uri            — URI MediaStore do oczekujacego zdjecia
  _pending_android_camera_path  — Kopia sciezki lokalnej

METODY:

  _photo_output_path() -> str
    - Generuje unikalna nazwe pliku: photo_YYYYMMDD_HHMMSS.jpg
    - Katalog: user_data_dir

  _is_image(path) -> bool [staticmethod]
    - Sprawdza rozszerzenie pliku (.jpg, .jpeg, .png, .bmp, .webp)
    - content:// URI sa traktowane jako obrazy

  capture_photo()
    - Sprawdza platforme (tylko Android)
    - Sprawdza/zadaje uprawnienia (CAMERA + lokalizacja)
    - Uruchamia _start_camera_capture()

  _start_camera_capture(output_path)
    - Wywoluje _camera_via_mediastore()
    - Obsluguje bledy

  _camera_via_mediastore(output_path)
    - Tworzy wpis w MediaStore (ContentValues z DISPLAY_NAME i MIME_TYPE)
    - Zapisuje URI w _pending_media_uri
    - Tworzy Intent ACTION_IMAGE_CAPTURE z EXTRA_OUTPUT
    - Uruchamia startActivityForResult (request_code=0x124)
    - Binduje callback on_activity_result

  _on_android_camera_result(request_code, result_code, intent_data) [@mainthread]
    - Obsluguje wynik z Activity aparatu
    - SUCCESS: kopiuje z content URI do pliku lokalnego, wywoluje _on_camera_complete
    - CANCEL: czysci URI, wyswietla komunikat
    - Zawsze unbinduje callback

  _copy_uri_to_file(uri, local_path) -> bool [staticmethod]
    - Kopiuje dane z content:// URI do pliku lokalnego
    - Uzywa Java Channels (FileOutputStream, transferFrom)
    - Waliduje rozmiar pliku wynikowego

  _delete_media_uri(uri)
    - Usuwa wpis MediaStore (czysci tymczasowy wpis)

  _fix_exif_orientation(path) [staticmethod]
    - Koryguje orientacje EXIF za pomoca Pillow (ImageOps.exif_transpose)
    - Zapisuje zdjecie bez danych EXIF (zapobiega podwojnej rotacji)

  _on_camera_complete(path) [@mainthread]
    - Wywoluje _fix_exif_orientation, _show_image
    - Wyswietla nazwe zaimportowanego zdjecia

  _on_file_selected(selection) [@mainthread]
    - Obsluguje wynik wyboru pliku (z aparatu lub file picker)
    - content:// URI: kopiuje do pliku lokalnego
    - Waliduje rozszerzenie, naprawia EXIF, wyswietla podglad


────────────────────────────────────────────────────────────────────────────────
 4.4  gps.py — GPSMixin
────────────────────────────────────────────────────────────────────────────────

Mixin zapewniajacy dostep do lokalizacji GPS.

KLASA POMOCNICZA:
  _GPSSingleListener (PythonJavaClass)
    - Implementuje interfejs android.location.LocationListener
    - Metody Java: onLocationChanged, onProviderEnabled,
      onProviderDisabled, onStatusChanged
    - onLocationChanged ustawia lokalizacje w kontenerze i sygnalizuje Event

  _get_gps_listener_class()
    - Leniwa inicjalizacja klasy listenera (singleton)

METODY GPSMixin:

  _get_gps_payload() -> dict[str, str]
    - Priorytet 1: Reczne wspolrzedne (dev_latitude, dev_longitude)
      - Zwraca {"gps": "lat,lon", "provider": "manual"}
    - Priorytet 2: Android GPS
      - Sprawdza uprawnienia lokalizacji
      - Pobiera swiezy fix (_request_fresh_location) + getLastKnownLocation
      - Porownuje lokalizacje z 3 providerow: GPS, NETWORK, PASSIVE
      - Wybiera najlepsza lokalizacje
      - Zwraca {"gps": "lat,lon", "provider": "...", "accuracy_m": "..."}
    - Desktop: zwraca pusty dict

  _is_better_location(new_location, current_best) [staticmethod]
    - Porownuje dwie lokalizacje
    - Kryterium: czas (max 2 min roznicy) i dokladnosc
    - Preferuje nowsze i dokladniejsze fixy

  _request_fresh_location(manager) [staticmethod]
    - Zadaje pojedynczy fix GPS i NETWORK PROVIDER jednoczesnie
    - Blokuje watek do 15 sekund (threading.Event.wait)
    - Pierwszy provider ktory odpowie — wygrywa
    - Czysci listenerow po zakonczeniu


────────────────────────────────────────────────────────────────────────────────
 4.5  permissions.py — PermissionsMixin
────────────────────────────────────────────────────────────────────────────────

Mixin obslugujacy uprawnienia systemu Android.

METODY:

  _android_permissions(camera_use=False, location_use=False) -> list
    - Buduje liste wymaganych uprawnien:
      * camera_use=True: Permission.CAMERA
      * location_use=True: ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION
      * Zawsze: READ_MEDIA_IMAGES (API 33+) lub READ_EXTERNAL_STORAGE (starsze)

  _android_permissions_granted(permissions) -> bool [staticmethod]
    - Sprawdza czy wszystkie podane uprawnienia sa nadane (check_permission)

  _has_any_location_permission() -> bool [staticmethod]
    - Sprawdza czy jest FINE lub COARSE location permission

  _request_android_permissions(permissions, callback) [staticmethod]
    - Wywoluje request_permissions z android.permissions
    - callback: funkcja (permissions, grants)

  _all_permissions_granted_result(grants) -> bool [staticmethod]
    - Normalizuje wynik callbacku (bool / int / str)
    - Obsluguje rozne formaty: True/False, 0/!=0, "granted"/"0"/"true"

CALLBACKI:
  _on_camera_permissions_result(permissions, grants) [@mainthread]
    - Jesli granty OK: uruchamia aparat
    - Jesli brak: wyswietla komunikat

  _on_picker_permissions_result(permissions, grants) [@mainthread]
    - Jesli granty OK: otwiera file picker
    - Jesli brak: wyswietla komunikat


────────────────────────────────────────────────────────────────────────────────
 4.6  server.py — ServerMixin
────────────────────────────────────────────────────────────────────────────────

Mixin zapewniajacy komunikacje z serwerem backendowym.

METODY POMOCNICZE:

  _server_image_output_path(suffix=".jpg") -> str
    - Generuje sciezke do pobranego obrazu serwera
    - Format: server_YYYYMMDD_HHMMSS_ffffff.{ext}

  _mime_type_for_path(image_path) -> str [staticmethod]
    - Mapuje rozszerzenie na MIME type
    - .png -> image/png, .webp -> image/webp, .bmp -> image/bmp
    - Domyslny: image/jpeg

  _to_wikimedia_thumb(url, width=400) -> str [staticmethod]
    - Konwertuje pelny URL Wikimedia Commons na URL miniatury
    - Regex: rozpoznaje pattern /[hash]/filename
    - Generuje: /thumb/[hash]/filename/{width}px-filename

PARSOWANIE ODPOWIEDZI:

  _extract_full_response(payload) -> dict
    - Parsuje kompletna odpowiedz JSON z serwera
    - Wyodrebnia nastepujace pola:

    Z payload.wiki:
      title           — Tytul artykulu Wikipedia
      description     — Opis artykulu
      wiki_url        — URL artykulu
      thumbnail/image — URL miniatury (dodaje do listy images)
      images          — Dodatkowe obrazy z Wikipedii

    Z payload.landmarks:
      confidence      — Pewnosc rozpoznania (konwertuje na procenty)
      name            — Nazwa obiektu (jesli brak title z wiki)

    Z payload:
      warning         — Ostrzezenie serwera
      message_labels  — Etykiety ostrzezen (lista lub string)
      message         — Wiadomosc (gdy brak landmarks)
      debug_log       — Log debugowania (string/dict/list -> string)
      nearby          — Lista pobliskich miejsc (title, wiki_url, thumbnail_url)

WYSYLANIE ZDJECIA:

  send_photo_to_server()
    - Walidacja: czy jest zdjecie, czy jest plikiem lokalnym
    - Walidacja: czy server_url zaczyna sie od http:// lub https://
    - Android: sprawdza uprawnienia lokalizacji
    - Wywoluje _start_sending()

  _start_sending(image_path)
    - Ustawia is_sending=True
    - Resetuje wszystkie pola odpowiedzi
    - Uruchamia watek roboczy (_send_photo_worker) jako daemon

  _send_photo_worker(image_path)
    - Czyta bajty zdjecia z pliku
    - Oczyszcza URL serwera z niedrukowalnych znakow
    - Pobiera dane GPS (_get_gps_payload)
    - Ustawia headery:
      * Accept: application/json
      * X-API-Key / Authorization: Bearer (jesli api_key jest ustawiony)
    - Wysyla POST multipart/form-data:
      * files: {"image": (filename, bytes, mime_type)}
      * data: gps_payload (gps, provider, accuracy_m)
    - Timeout: 120 sekund
    - Parsuje odpowiedz: _extract_full_response()
    - Pobiera obrazy: _download_images_progressive()
    - Pobiera miniatury pobliskich: _download_nearby_images()

    OBSLUGA BLEDOW:
      HTTPError        — "Blad serwera HTTP {code}" + URL + body (180 znakow)
      ConnectionError  — "Brak polaczenia z serwerem"
      Timeout          — "Przekroczono czas oczekiwania na serwer"
      JSONDecodeError  — "Serwer nie zwrocil poprawnego JSON"
      Exception        — "Blad wysylki: {exc}"

CALLBACKI:

  _on_send_permissions_result(permissions, grants) [@mainthread]
    - Obsluguje wynik prosba o uprawnienia lokalizacji przed wyslaniem

  _on_send_success(extracted) [@mainthread]
    - Aktualizuje wszystkie wlasciwosci Kivy danymi z serwera
    - Buduje galerie zdjec i sekcje pobliskich
    - Przechodzi na ekran odpowiedzi

  _on_send_failed(error_message) [@mainthread]
    - Wyswietla komunikat bledu, resetuje is_sending

POBIERANIE OBRAZOW:

  _download_images_progressive(urls)
    - Pobiera do 5 obrazow z listy URLs
    - Konwertuje na miniatury Wikimedia (400px)
    - Zapisuje lokalne kopie
    - Dodaje kazdy obraz do galerii (_add_gallery_image)
    - User-Agent: "VirtualGuide/1.0 (Kivy; +https://github.com)"
    - Timeout: 15s na obraz

  _download_nearby_images(nearby_items)
    - Pobiera miniatury pobliskich obiektow
    - Aktualizuje widgety w kontenerze nearby (_update_nearby_image)


────────────────────────────────────────────────────────────────────────────────
 4.7  env.py — Konfiguracja srodowiskowa
────────────────────────────────────────────────────────────────────────────────

  read_local_env(env_path) -> dict[str, str]
    - Czyta plik .env z katalogu projektu
    - Ignoruje: puste linie, komentarze (#), linie bez "="
    - Obsluguje cudzyslow (podwojne i pojedyncze)
    - Zwraca dict klucz-wartosc

  ENV = read_local_env(Path(__file__).with_name(".env"))
    - Globalny slownik konfiguracji

  Oczekiwane klucze w .env:
    SERVER_URL  — URL endpointu serwera
    API_KEY     — Klucz autoryzacji API


================================================================================
 5. INTERFEJS UZYTKOWNIKA (photo_app.kv)
================================================================================

Aplikacja sklada sie z 3 ekranow zarzadzanych przez ScreenManager:

────────────────────────────────────────────────────────────────────────────────
 5.1  Ekran "import" — Glowny ekran
────────────────────────────────────────────────────────────────────────────────

  ELEMENTY:
    - Naglowek "Virtual Guide" (24sp, bold)
    - Podtytul instrukcji
    - Label statusu (niebieski, powiazany z app.status_text)
    - Podglad zdjecia (Image, ukryty gdy brak zdjecia)
    - Przyciski:
      * "Zrob zdjecie"    -> app.capture_photo()
      * "Importuj zdjecie" -> app.pick_photo()
    - Przycisk "Wyslij do przewodnika" / "Wysylanie..."
      * Zablokowany gdy: is_sending=True LUB brak image_path
    - Overlay spinnera (widoczny podczas wysylania):
      * Widget spinner_widget (animowany luk)
      * Label "Analizowanie..."
    - Przycisk "SET" (prawy gorny rog) -> app.open_developer_settings()

────────────────────────────────────────────────────────────────────────────────
 5.2  Ekran "response" — Wynik analizy
────────────────────────────────────────────────────────────────────────────────

  Ekran scrollowalny (ScrollView) z sekcjami:

    1. ETYKIETY OSTRZEZEN (guide_message_labels)
       - Czerwony tekst na ciemno-czerwonym tle
       - Widoczne tylko gdy niepuste

    2. ORYGINALNE ZDJECIE
       - Wyswietla przeslane zdjecie (200dp)

    3. TYTUL (guide_title)
       - 22sp, bold, bialy

    4. PEWNOSC (guide_confidence)
       - "Pewnosc: XX.X%" (niebieski)

    5. OPIS
       - Naglowek "Opis" (16sp, szary)
       - Tekst guide_text (bialy)

    6. PRZYCISK WIKIPEDIA
       - Zielone tlo, widoczny gdy wiki_url jest ustawiony
       - Otwiera strone Wikipedia w przegladarce

    7. GALERIA ZDJEC
       - Naglowek "Zdjecia"
       - Poziomy ScrollView z GridLayout (1 wiersz)
       - Zdjecia 300x300 z serwera/Wikipedii

    8. OSTRZEZENIE (guide_warning)
       - Zolty tekst "Uwaga: ..."

    9. WIADOMOSC (guide_message)
       - Tekst gdy nie rozpoznano obiektu

   10. POBLISKIE OBIEKTY (guide_nearby)
       - Naglowek "Prawdopodobne obiekty w poblizu"
       - GridLayout z dynamicznymi kartami

   11. PRZYCISKI
       - "Debug Log" -> app.go_to_debug_log_screen()
       - "Powrot"    -> app.back_to_import_screen()

    - Przycisk "SET" (prawy gorny rog)

────────────────────────────────────────────────────────────────────────────────
 5.3  Ekran "debug_log" — Log debugowania
────────────────────────────────────────────────────────────────────────────────

  ELEMENTY:
    - Naglowek "Debug Log" (22sp)
    - ScrollView z TextInput (readonly)
      * Wyswietla guide_debug_log
      * Ciemne tlo, jasny tekst
    - Przycisk "Kopiuj calosc" -> app.copy_debug_log()
    - Przycisk "Powrot"        -> app.back_to_response_screen()


================================================================================
 6. KOLORYSTYKA UI (CIEMNY MOTYW)
================================================================================

  Tlo aplikacji:        rgba(0.08, 0.10, 0.14, 1)   — bardzo ciemny granat
  Tekst podstawowy:     rgba(0.96, 0.97, 1.00, 1)   — prawie bialy
  Tekst drugorzedny:    rgba(0.70, 0.74, 0.82, 1)   — szary
  Tekst statusu/akcent: rgba(0.55, 0.78, 1.00, 1)   — niebieski
  Przyciski glowne:     rgba(0.20, 0.35, 0.70, 1)   — niebieski
  Przycisk Wikipedia:   rgba(0.15, 0.45, 0.15, 1)   — zielony
  Przycisk SET/Debug:   rgba(0.24, 0.28, 0.36, 1)   — ciemny szary
  Ostrzezenie:          rgba(1.00, 0.75, 0.20, 1)   — zolty
  Blad/label:           rgba(1.00, 0.30, 0.30, 1)   — czerwony


================================================================================
 7. PRZEPLYW DZIALANIA APLIKACJI
================================================================================

  1. URUCHOMIENIE
     main.py -> PhotoApp().run()
     -> build(): laduje .env, ustawienia deweloperskie, KV layout

  2. IMPORT ZDJECIA (ekran "import")
     Uzytkownik wybiera jedna z opcji:
     a) "Zrob zdjecie":
        -> capture_photo()
        -> sprawdz uprawnienia (CAMERA + lokalizacja)
        -> otworz natywna aplikacje aparatu (Intent ACTION_IMAGE_CAPTURE)
        -> odczytaj zdjecie z MediaStore URI
        -> skopiuj do pliku lokalnego
        -> napraw orientacje EXIF
        -> pokaz podglad

     b) "Importuj zdjecie":
        -> pick_photo()
        -> sprawdz uprawnienia (READ_MEDIA_IMAGES)
        -> otworz file picker (plyer lub Kivy)
        -> skopiuj content:// URI do pliku (jesli Android)
        -> napraw orientacje EXIF
        -> pokaz podglad

  3. WYSLANIE DO SERWERA
     -> send_photo_to_server()
     -> walidacja: plik istnieje, URL poprawny
     -> sprawdz uprawnienia lokalizacji (Android)
     -> _start_sending(): is_sending=True, reset pol
     -> watek roboczy:
        -> odczytaj bajty zdjecia
        -> pobierz dane GPS
        -> POST multipart na server_url
        -> parsuj JSON odpowiedz
        -> pobierz obrazy galerii (do 5)
        -> pobierz miniatury pobliskich

  4. WYSWIETLENIE WYNIKOW (ekran "response")
     -> _on_send_success(): aktualizuj properties
     -> _populate_image_gallery(): buduj widgety galerii
     -> _populate_nearby(): buduj karty pobliskich
     -> _go_to_response_screen(): zmien ekran

  5. INTERAKCJA NA EKRANIE WYNIKOW
     -> Open Wikipedia -> webbrowser.open(wiki_url)
     -> Debug Log -> ekran debug_log
     -> Powrot -> ekran import


================================================================================
 8. KOMUNIKACJA Z SERWEREM — PROTOKOL
================================================================================

ENDPOINT: POST {server_url}
CONTENT-TYPE: multipart/form-data

REQUEST:
  Headers:
    Accept: application/json
    X-API-Key: {api_key}          (opcjonalnie)
    Authorization: Bearer {api_key}  (opcjonalnie)

  Body (multipart):
    image    — plik zdjecia (filename, bytes, mime_type)
    gps      — wspolrzedne "lat,lon"  (opcjonalnie)
    provider — zrodlo GPS: "gps"/"network"/"passive"/"manual"  (opcjonalnie)
    accuracy_m — dokladnosc w metrach  (opcjonalnie)

RESPONSE (JSON):
  {
    "wiki": {
      "title": "Nazwa obiektu",
      "description": "Opis z Wikipedii...",
      "url": "https://pl.wikipedia.org/wiki/...",
      "thumbnail": "https://upload.wikimedia.org/...",
      "images": ["url1", "url2", ...]
    },
    "landmarks": [
      {
        "name": "Nazwa",
        "confidence": 0.953
      }
    ],
    "warning": "Opcjonalne ostrzezenie",
    "message": "Wiadomosc gdy brak wynikow",
    "message_labels": ["label1", "label2"],
    "nearby": [
      {
        "title": "Pobliski obiekt",
        "url": "https://...",
        "thumbnail": "https://..."
      }
    ],
    "debug_log": "..."
  }


================================================================================
 9. UPRAWNIENIA ANDROID
================================================================================

Deklaracja w buildozer.spec (AndroidManifest.xml):
  - CAMERA                  — dostep do aparatu
  - READ_EXTERNAL_STORAGE   — odczyt plikow (API < 33)
  - READ_MEDIA_IMAGES       — odczyt obrazow (API 33+)
  - ACCESS_FINE_LOCATION    — dokladna lokalizacja GPS
  - ACCESS_COARSE_LOCATION  — przyblizona lokalizacja
  - INTERNET                — komunikacja sieciowa

Uprawnienia sa zadane dynamicznie (runtime permissions) w zaleznosci
od kontekstu:
  - Robienie zdjecia: CAMERA + lokalizacja + zdjecia
  - Import zdjecia: zdjecia
  - Wysylanie: lokalizacja


================================================================================
 10. ZALEZNOSCI
================================================================================

  requirements.txt:
    kivy==2.3.0       — Framework UI (widgety, layout, ekrany)
    plyer==2.1.0      — Natywne API (file picker na Android)
    requests==2.32.3  — Klient HTTP (wysylanie na serwer, pobieranie)
    Pillow==10.4.0    — Obrobka obrazow (rotacja EXIF)

  Dodatkowe (tylko Android, via python-for-android):
    pyjnius           — Most Python-Java (android.*, jnius)
    android           — Android-specyficzne API (permissions, activity)


================================================================================
 11. KONFIGURACJA BUILDOZER (buildozer.spec)
================================================================================

  title:              Virtual Guide
  package.name:       virtualguide
  package.domain:     com.mierzwu
  version:            0.1.0
  orientation:        portrait
  fullscreen:         0 (nie)
  android.api:        34 (target)
  android.minapi:     21 (minimum)
  android.ndk:        25c
  p4a.bootstrap:      sdl2
  source.include_exts: py, png, jpg, kv, atlas
  source.exclude_dirs: tests, bin, venv, .git, __pycache__


================================================================================
 12. KONFIGURACJA SRODOWISKA (.env)
================================================================================

  Plik .env w katalogu glownym projektu (obok main.py):

    SERVER_URL=https://twoj-serwer.com/api/analyze
    API_KEY=twoj-klucz-api

  Zmienne te sa domyslnymi wartosciami. Moga byc nadpisane przez
  ustawienia deweloperskie (popup "SET"), ktore sa zapisywane
  w developer_settings.json w katalogu danych aplikacji.


================================================================================
 13. WATEK I BEZPIECZENSTWO WATKOW
================================================================================

  Aplikacja uzywa modelu watkowego Kivy:
  - Glowny watek (UI): obsluguje zdarzenia, renderowanie, aktualizacje
  - Watek roboczy (daemon): komunikacja sieciowa (send_photo_worker)

  Synchronizacja:
  - Dekorator @mainthread gwarantuje wykonanie na watku UI
  - Odpowiedzi serwera sa przekazywane na watek UI przez @mainthread
  - GPS: threading.Event do synchronizacji fixu lokalizacji (15s timeout)

  Zasady:
  - Widgety Kivy NIGDY nie sa modyfikowane z watku roboczego
  - Wszystkie modyfikacje UI przez _on_send_success/_on_send_failed
  - Clock.schedule_once/schedule_interval dla opoznionych operacji UI


================================================================================
 14. OBSLUGA BLEDOW
================================================================================

  Aplikacja obsluguje bledy na kilku poziomach:

  BLEDY APARATU:
  - Brak uprawnien -> komunikat + ponowna prosba
  - Anulowanie aparatu -> "Anulowano aparat"
  - Blad kopiowania URI -> "Nie udalo sie zapisac zdjecia"

  BLEDY FILE PICKER:
  - Brak uprawnien -> komunikat + ponowna prosba
  - Brak wyboru -> "Nie wybrano pliku"
  - Niepoprawny format -> "Wybrany plik nie jest zdjeciem"

  BLEDY SERWERA:
  - HTTP 4xx/5xx -> "Blad serwera HTTP {code}" + body
  - Brak polaczenia -> "Brak polaczenia z serwerem"
  - Timeout (120s) -> "Przekroczono czas oczekiwania na serwer"
  - Bledny JSON -> "Serwer nie zwrocil poprawnego JSON"

  BLEDY GPS:
  - Brak uprawnien -> pusty payload (zdjecie wysylane bez GPS)
  - Brak providera -> pusty payload
  - Timeout (15s) -> uzywa getLastKnownLocation

  BLEDY POBIERANIA OBRAZOW:
  - Blad sieci -> obraz pomijany (continue)
  - Pusty content -> pomijany


================================================================================
 15. PERSISTENCJA DANYCH
================================================================================

  developer_settings.json (JsonStore w user_data_dir):
    - server_url
    - api_key
    - dev_latitude
    - dev_longitude

  Pliki tymczasowe (user_data_dir):
    - photo_YYYYMMDD_HHMMSS.jpg        — zdjecia z aparatu/importu
    - server_YYYYMMDD_HHMMSS_ffffff.jpg — obrazy pobrane z serwera

  Pliki te sa przechowywane w prywatnym katalogu danych aplikacji
  na Androidzie (wewnetrzna pamiec).


================================================================================
