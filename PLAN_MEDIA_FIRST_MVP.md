# Plan: Media-First MVP — Krok 1 (backend + dane)

**Data:** 2026-09-20
**Status:** Design — po pełnej analizie ryzyk; implementacja dopiero po wyraźnej decyzji usera
**Cel:** Fundament pod media-first product: dane per-mecz (raport tygodnia, forma, trend) bez ruszania działającej aplikacji.

---

## Kontekst

Pivot produktu: z klasycznego SaaS na media-first (20.09.2026). Rdzeń: „wracaj regularnie, bo tu najszybciej zrozumiesz, co dzieje się z polskimi piłkarzami za granicą".

MVP odpowiada na 3 pytania:
1. Kto z Polaków grał i jak mu poszło (raport tygodnia)?
2. Kto jest teraz w formie (ranking formy)?
3. Jak wypaida jeden zawodnik na tle drugiego (porównywarka — istnieje)?

**Kolejność (podejście A):** najpierw backend + dane (ten plan), potem Next.js app.

**Frontend:** produkt publiczny = Next.js (osobne repo, SEO). Streamlit zostaje jako panel wewnętrzny.

**Ograniczenie:** RapidAPI wyłączone (limit darmowy za mały). Implementacja i testy na mockach; backfill + pierwszy raport po wykupieniu miesiąca testowego.

---

## Co zostaje bez zmian

- `sync_full.py` — logika parsowania i agregacji (dodajemy tylko zapis match logs)
- Wszystkie istniejące tabele i endpointy
- Streamlit app, live tracking, heatmapy, admin

---

## Sekcja 1: Nowa tabela `player_match_logs`

Jeden wiersz = jeden występ zawodnika w jednym meczu.

| Pole | Typ | Opis |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `player_id` | FK → players (CASCADE), NOT NULL | |
| `match_id` | INTEGER NOT NULL | RapidAPI event id |
| `season` | VARCHAR(10) NOT NULL | „2025/26" |
| `match_date` | DATE NOT NULL | UTC |
| `competition_name` / `competition_type` / `competition_id` | NOT NULL (name/type) | league / european / domestic |
| `opponent` | VARCHAR(100) NOT NULL | |
| `is_home` | BOOLEAN NOT NULL | |
| `score` | VARCHAR(20) NULL | „2:1" — patrz Sekcja 3, punkt B |
| `minutes` | INTEGER NOT NULL DEFAULT 0 | |
| `goals`, `assists`, `yellow_cards`, `red_cards` | INTEGER NOT NULL DEFAULT 0 | |
| `appearance` | VARCHAR(10) NOT NULL | `start` / `sub` / `bench` |
| `rating` | NUMERIC(4,2) NULL | |
| `created_at` | TIMESTAMP NOT NULL | |

**Constraints:**
- `UNIQUE(player_id, match_id)` — twarda gwarancja braku duplikatów na poziomie bazy.
- Zapis przez `INSERT ... ON CONFLICT (player_id, match_id) DO UPDATE` — **upsert idempotentny**: ponowne przetworzenie meczu nadpisuje wiersz świeżymi danymi zamiast go zduplikować (i poprawia dane, gdyby API je zrewidowało). Wzorzec już używany w projekcie dla heatmap (sync_full.py:1056–1079).
- Indeksy: `(player_id, match_date DESC)` — profil i forma; `(match_date)` — raport tygodnia; `(season)`.

Uwaga: obecnie parser zwraca `None` dla zawodnika bez minut i bez zdarzeń. Przy zapisie match logs taki przypadek logujemy jako `appearance='bench'` (sekcja „bez minut" w raporcie). To **nie wpływa** na agregaty — liczniki per konkurencja rosną tylko dla występów z minutami.

## Sekcja 2: Nowa tabela `weekly_reports`

| Pole | Typ |
|---|---|
| `id` | BIGSERIAL PK |
| `season` | VARCHAR(10) NOT NULL |
| `period_start` / `period_end` | DATE NOT NULL |
| `title` | VARCHAR(200) NOT NULL |
| `editorial_comment` | TEXT NULL |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'draft' |
| `generated_at` / `published_at` | TIMESTAMP |

**Constraint:** `UNIQUE(period_start, period_end)`. `POST /reports/generate` dla istniejącego okresu = upsert na tym constraint (regeneracja draftu nie tworzy duplikatu raportu).
**Workflow:** system generuje draft z match_logs → user dopisuje komentarz → publikacja. Archiwum = lista `published` (rosnąco po `period_start`).

## Sekcja 3: Zmiana w `sync_full.py`

### A. Zapis match logs
W pętli przetwarzania lineupów (okolice sync_full.py:947–1024):
1. Występ z minutami → upsert z `appearance='start'`/`'sub'` + minuty, gole, asysty, kartki, rating.
2. Występ `bench` (parser zwrócił None, gracz w liście subs) → upsert z `minutes=0`.
3. Agregacja: **bez żadnych zmian** — liczniki per konkurencja rosną dokładnie tak jak dziś.

### B. Nowo odkryte braki do uzupełnienia (analiza 20.09.2026)
Obecnie `team_matches` przenosi tylko `event_id, is_home, home_name, away_name` (sync_full.py:894–899):
- **`match_date` nie jest przechwytywany** — `_extract_match_date` istnieje, ale nigdy nie jest wywołany (martwy kod). Trzeba rozszerzyć `team_matches` o datę z surowej odpowiedzi API (prawdopodobnie `startTimestamp`).
- **`score` nie jest przenoszony** — wynik meczu pobierany jest tylko dla GK (2 dodatkowe wywołania API). Score do uzupełnienia z danych listy meczów, jeśli API je zwraca; inaczej `NULL` (nie dokupujemy wywołań).
- **Weryfikacja nazw pól API przy pierwszym prawdziwym syncu** — to jedyne miejsca, których nie da się potwierdzić na mockach. Zostaną sprawdzone na 1 meczu w trybie `--dry-run --player` przed backfillem.

### C. Zweryfikowane bezpieczeństwo agregacji (2026-09-20)

- `aggregate_to_season_total` (sync_full.py:1251) — buduje sumy **od zera** z `player_stats_by_competition` i nadpisuje. Idempotentne. ✅
- `player_stats_by_competition` — tryb domyślny (incremental) **DODAJE** (sync_full.py:1200–1235): ponowne przetworzenie meczu w tym trybie podwoiłoby liczby. Tryb `--full` / `--player` **ZASTĘPUJE** świeżo policzonymi danymi i ostrzega, gdy nowych danych < starych (sync_full.py:1168–1199). ✅
- **Żelazna reguła: backfill wyłącznie w trybie `--full`. Nigdy incremental z wymuszonym ponownym przetwarzaniem.**
- Dedup incremental: `is_match_synced` + `last_match_id` (sync_full.py:920–926); mecz oznaczany jako zsynchronizowany tylko gdy Polski gracz zagrał (sync_full.py:1103–1105) — mecz z Polakiem tylko na ławce jest ponownie sprawdzany przy kolejnym syncu (koszt: kilka wywołań API, zero ryzyka dla liczb; upsert w match_logs i tak deduplikuje).

### D. Ochrona przed równoległym syncem (best practice)
Dwa równoległe synci (np. zombie proces — znany problem na Windows) mogą podwoić liczby w trybie incremental. Dodajemy **blokadę na poziomie bazy**: `SELECT pg_advisory_lock(...)` na starcie syncu i zwolnienie na końcu — drugi równoległy sync czeka zamiast się ścigać. Mała zmiana, eliminuje całą klasę błędów.

## Sekcja 4: Nowe endpointy

| Endpoint | Auth | Do czego |
|---|---|---|
| `POST /reports/generate?start&end` | admin | generuje draft raportu z match_logs |
| `PATCH /reports/{id}` | admin | zapis komentarza / publikacja |
| `GET /reports/latest` | publiczny | najnowszy opublikowany |
| `GET /reports/archive` | publiczny | lista raportów (archiwum/SEO) |
| `GET /rankings/form?matches=5&position=` | publiczny | ranking formy (GK osobno) |
| `GET /players/{id}/matches?limit=` | publiczny | ostatnie mecze (profil) |
| `GET /players/{id}/form?matches=5` | publiczny | forma / trend |

Porównywarka MVP korzysta z istniejących endpointów stats — bez nowego endpointu.

### Przełącznik sezonów (wymaganie usera, 20.09.2026)
- **Wszystkie endpointy odczytu** (nowe i istniejące) przyjmują parametr `?season=`, domyślnie = sezon z configu (Krok 0). Część już ma (`/stats`, `/detailed-stats`) — ujednolicić defaulty.
- **Frontend (Krok 2, Next.js):** przełącznik sezonu w menu; domyślnie bieżący sezon.
- **Semantyka:** sezon bieżący = pełne dane (mecze, forma, raporty); sezon 2025/26 = tylko statystyki sezonowe i per konkurencja (bez match logs / formy / raportów — tych dane nie istnieją). Endpointy zwracają pustą listę / 404 z czytelnym komunikatem, nie błąd.
- `GET /filters` rozszerzamy o listę dostępnych sezonów (distinct z `player_stats`) — frontend buduje przełącznik z tego, co faktycznie jest w bazie.
Logika formy w backendzie: `app/services/form.py` (czysta funkcja, testowalna):
- zawodnik z pola: minuty + gole×3 + asysty×2 + rating (średnia ważona) z ostatnich N meczów
- GK: minuty + clean sheets×3 + rating
- score normalizowany, sortowanie malejąco

**Rozszerzenie po MVP — obronione rzuty karne w nocie GK (decyzja usera, 25.09.2026):** docelowo obronione karne muszą mieć wpływ na notę bramkarza. Wymaga to rozszerzenia `player_match_logs` o kolumny per-mecz (np. `saves`, `penalties_saved`) + rozszerzenia parsera w syncu; dopiero potem dodanie składnika do wzoru GK w `form.py`. Nie robimy w MVP — zapisane jako wymaganie na przyszłość (kolejność: najpierw sprawdzić, czy API w ogóle zwraca te dane w lineupach).

## Sekcja 5: Backfill (jednorazowo, po wykupieniu API)

> **Zakres zaktualizowany (Sekcja 8.3):** backfill obejmuje wyłącznie sezon 2026/27 od sierpnia 2026 — nie cofamy się do 2025/26.

**Tryb: wyłącznie `--full`** (zastępuje agregaty, deduplikuje match logs przez upsert).

Kolejność (każdy krok = osobna bramka kontrolna):
1. **Snapshot kontrolny** — zapisać obecne wartości `player_stats` i `player_stats_by_competition` (select przed backfillem, np. do pliku CSV).
2. `--full --dry-run --player <id>` — 1 zawodnik: weryfikacja nazw pól API (data, score — Sekcja 3B) i liczby wywołań.
3. `--full --player <id>` — realny backfill 1 zawodnika.
4. **Bramka weryfikacyjna A** (po kroku 3): porównanie ze snapshotem dla tego zawodnika — identyczne lub wyjaśnione różnice; zapytanie o duplikaty w match_logs (group by player_id, match_id having count>1 → musi zwrócić 0 wierszy).
5. `--full --dry-run` całość — potwierdzenie finalnego kosztu (szacunek wstępny: ~100–150 meczów × 1 wywołanie lineup + odpytania lig = **300–450 wywołań**; dokładna liczba z dry-runu).
6. `--full` całość.
7. **Bramka weryfikacyjna B** (finalna): porównanie snapshot vs nowe wartości dla wszystkich zawodników; duplikaty = 0; `count(match_logs)` vs liczba przetworzonych meczów zgadza się w granicach występów.
8. **Weryfikacja baseline'u ratingu (decyzja 25.09.2026: zostać przy 6.0 do czasu danych):** po backfillu sprawdzić rzeczywistą średnią/medianę `rating` w `player_match_logs` (jedno zapytanie). Jeśli realna średnia ≠ ~6.0 (np. wyjdzie 6.5 jak w typowych systemach SofaScore-style), skorygować `RATING_BASELINE` w `app/services/form.py` (1 stała + testy), żeby „przeciętny" mecz pozostawał neutralny. Zmiana baseline'u przesuwa wszystkie noty równo (±10 pkt na 100 za każdy punkt) — kolejność rankingu prawie się nie zmienia.

## Sekcja 6: Pełny rejestr ryzyk

### Ryzyka duplikatów / błędów danych

| # | Ryzyko | Prawdopodob. | Mitygacja | Gwarancja |
|---|---|---|---|---|
| 1 | Ten sam występ zapisany 2× | — | `UNIQUE(player_id, match_id)` + upsert | **Baza fizycznie nie pozwoli na duplikat** |
| 2 | Ten sam mecz przetworzony przez 2 drużyny (Polacy po obu stronach) | niskie | wiersze różnią się `player_id` — to nie duplikat, to 2 występy | unikalność per zawodnik |
| 3 | Podwójne agregaty przy ponownym przetwarzaniu | średnie | backfill tylko `--full` (replace); reguła zapisana w planie i w kodzie (guard: `--full` required dla backfilla) | Sekcja 3C |
| 4 | Równoległe synci (zombie proces) | znane na Windows | advisory lock (Sekcja 3D) + `tasklist \| findstr python` przed uruchomieniem | blokada w bazie |
| 5 | Mecz z Polakiem na ławce przetwarzany wielokrotnie | pewne (z designu) | nic nie dodaje do agregatów; match_logs deduplikuje upsert | koszt: kilka wywołań API |
| 6 | API zwraca błąd / 503 w połowie | średnie | retry z backoff już istnieje; przy failed league → `continue` bez zapisu (nie ma utraty danych, są braki — dość doczyścić przy kolejnym syncu) | brak częściowych zapisów |
| 7 | Zmiana/przegląd danych przez API (rewizja statystyk) | niskie | upsert DO UPDATE nadpisuje świeżymi danymi | dane zawsze najświeższe |
| 8 | transfer zawodnika w trakcie sezonu (2 kluby) | możliwy | player_id wewnętrzny stabilny, mecze różnych klubów różne | bez konfliktu |
| 9 | raport wygenerowany 2× dla tego samego okresu | — | `UNIQUE(period_start, period_end)` + upsert | brak duplikatu raportu |

### Bezpieczeństwo / best practices

| Obszar | Zabezpieczenie |
|---|---|
| SQL injection | wyłącznie SQLAlchemy ORM (parametryzowane) — zero raw SQL z inputem |
| Walidacja wejścia | Pydantic: daty ISO `YYYY-MM-DD`, `limit ≤ 50`, `matches ∈ {3,5,10}`, `position ∈ {GK,field}`; nieznane → 422 |
| Auth | publiczne = tylko GET (read-only, same publiczne dane sportowe); zapis (generate/PATCH) = istniejący mechanizm admin jak w `/admin/sync` |
| Rate limiting | istniejący globalny slowapi obejmuje nowe endpointy automatycznie |
| Ujawnianie błędów | jak po audycie 2026-05-25: ogólne komunikaty, bez stacktrace/DB details |
| Sekrety | żadnych nowych zmiennych env poza istniejącymi; brak sekretów w logach |
| FK / integralność | `player_id` FK CASCADE (spójne z resztą schematu); NOT NULL na polach obowiązkowych |
| Strefy czasowe | `match_date` w UTC (spójnie z resztą projektu) |
| XSS | komentarz redakcyjny renderowany jako tekst — React (Next.js) escapuje domyślnie; Streamlit nie interpretuje HTML bez `unsafe_allow_html` |
| RLS Supabase | nieskonfigurowane (świadomie, jak dziś) — do odesłania do Fazy auth przy Etapie 3 |

### Uczciwe zastrzeżenie
„Zero ryzyka" nie istnieje, ale: (a) żadna operacja w tym planie **nie usuwa** danych, (b) duplikaty w nowej tabeli są **fizycznie niemożliwe** przez constraint bazy, (c) każde uruchomienie na prawdziwych danych ma bramkę weryfikacyjną z snapshotem. Worst case = zmarnowane wywołania API, nie uszkodzone dane. Jedyne nieweryfikowalne na mockach (nazwy pól API: data/score) sprawdzamy na 1 meczu przed backfillem (Sekcja 5, krok 2).

## Sekcja 7: Testy

**Testy jednostkowe (bez API, na mockach):**
- `services/form.py`: score formy — zawodnik pola / GK / brak meczów / remisy
- zapis match logs: ten sam mecz 2× → 1 wiersz (upsert); bench vs start vs sub
- raporty: generate → upsert na okres; publish → latest/archive zwraca tylko published
- endpointy: walidacja parametrów (422 na śmieciach), limit bounded

**Testy integracyjne po backfillu (bramki A i B z Sekcji 5).**

## Kolejność implementacji (po akceptacji)

**Krok 0: Przełączenie na sezon 2026/27** (warunek startu — patrz Sekcja 8)

1. ✅ **GOTOWE (20.09.2026):** config sezonu — `current_season` w `app/core/config.py` (default „2026/27", env `CURRENT_SEASON`), podmienione hardcody w sync_full.py / players.py / heatmaps.py / live_poller.py. Testy: `tests/test_config.py` (TDD). Zmiany lokalne, NIEzacommitowane. 71 testów passed, zero nowych błędów mypy.
2. Migracja: 2 tabele (SQL w Supabase)
2. Advisory lock w syncu
3. Rozszerzenie `team_matches` o datę (+score jeśli dostępny) — z weryfikacją pól API
4. Zapis match logs w syncu + testy na mockach
5. `services/form.py` + testy
6. Endpointy raportów/formy/mecze + testy
7. *(po wykupieniu API)* backfill od początku sezonu 2026/27 (sierpień 2026) wg Sekcji 5 z bramkami weryfikacyjnymi
8. Krok 2 (osobny plan): Next.js app — Start / Raport tygodnia / Zawodnicy / Ranking formy / Porównywarka / Archiwum

---

## Sekcja 8: Przełączenie sezonu na 2026/27 + aktualizacja zawodników

**Decyzja usera (20.09.2026):** media-first startuje od sezonu 2026/27. Dane 2025/26 zostają w bazie jako historia (nie ruszamy). Wielu zawodników zmieniło drużyny — potrzebna aktualizacja listy.

### 8.1 Przełączenie sezonu

Sezon `2025/26` jest zahardkodowany w ~8 miejscach:
- `sync_full.py:537` (`CURRENT_SEASON`), `sync_full.py:1059` (heatmapy — literał)
- `app/api/v1/players.py:127`, `app/api/v1/players.py:250` (defaulty endpointów)
- `app/api/v1/heatmaps.py:26` (default parametru)
- `app/services/live_poller.py:1278`
- `app/db/models.py` — domyślne wartości kolumn

**Zmiana:** jedna wartość sezonu w configu (`app/config.py`), z której czytają wszystkie powyższe miejsca. Replace-all w 8 miejscach byłby pułapką przy kolejnej zmianie sezonu (2027/28).

> ⚠️ **UWAGA NA PRZYSZŁOŚĆ (decyzja usera, 20.09.2026): default sezonu = 2026/27 od razu w kodzie.**
> **Kolejność przy deployu MUSI być:** najpierw backfill danych sezonu 2026/27 (po wykupieniu API), dopiero potem deploy kodu z nowym defaultem. Deploy przed backfillem = produkcja (Render + Streamlit) pokazuje pusty sezon, bo endpointy będą odpytywać 2026/27, którego jeszcze nie ma w bazie.

**Bezpieczeństwo przełączenia:**
- `player_stats`: `UNIQUE(player_id, season)` → sezon 2026/27 = nowe wiersze, 2025/26 nietknięte ✅
- `player_stats_by_competition`: `UNIQUE(player_id, season, competition_type, competition_name)` → jw. ✅
- `sync_state`: `UNIQUE(team_id, competition_id, season)` → świeże stany inkrementalne dla nowego sezonu ✅
- `synced_matches`: brak kolumny sezonu, ale `match_id` jest globalnie unikalne w API → brak konfliktów ✅
- `player_heatmap_positions`: sezon w kluczu unikalnym ✅

### 8.2 Aktualizacja zawodników (transfery + nowi)

Ręczna kuracja słowników w `sync_full.py`:
1. `POLISH_PLAYERS` — źródło prawdy; dodać nowych (wymaga `rapidapi_id`), oznaczyć/usunąć odeszłych
2. `TEAMS` — nowe drużyny z ich konkurencjami (league_id)
3. `PLAYER_TEAMS` — przypisanie zawodnik → team_id po transferach

**Wejście od usera:** lista transferów i nowo śledzonych zawodników.
**Wyszukanie `rapidapi_id`:** po wykupieniu API (endpointy search) lub przez SofaScore (ID zwykle identyczne).
**Weryfikacja:** po dodaniu — `sync_full.py --player <id> --dry-run` dla każdego nowego zawodnika przed pierwszym pełnym synciem.

#### 8.2.1 Zasada: baza = wynik, słowniki = kontrola

Bazy Supabase **nie edytujemy ręcznie** przy transferach. Słowniki w `sync_full.py` (`POLISH_PLAYERS` / `TEAMS` / `PLAYER_TEAMS`) są listą kontrolną — sync sam tworzy/aktualizuje wiersze w bazie (`players` get-or-create, statystyki przez upsert). Edycja słowników + sync = kompletna "aktualizacja bazy piłkarzy".

#### 8.2.2 Kiedy: PRZED backfillem, PO wykupieniu API

Kolejność obowiązkowa (łamana kolejność = powtórzona praca lub pusty sezon na produkcji):

1. Wykupienie miesiąca API (dopiero wtedy dostępne endpointy search do znajdowania `rapidapi_id`)
2. **Aktualizacja słowników** (transfery + nowi) — przed jakimkolwiek syncem sezonu 2026/27, bo backfill idzie klub po klubie: zawodnik przypisany do starego klubu = brak jego nowych meczów
3. Backfill sezonu 2026/27 wg Sekcji 5 (bramki: dry-run → 1 zawodnik → snapshot → całość)
4. Deploy kodu z nowym defaultem sezonu (reguła z 8.1)

#### 8.2.3 Jak, krok po kroku

| Przypadek | Co zrobić | Efekt w bazie |
|---|---|---|
| **Transfer** (ten sam zawodnik, nowy klub) | zmiana `team_id` w `PLAYER_TEAMS` (+ nowy klub w `TEAMS` jeśli trzeba) | mecze nowego klubu liczą się do sezonu 2026/27; historia 2025/26 nietknięta |
| **Nowy zawodnik za granicą** | znaleźć `rapidapi_id` → dodać do `POLISH_PLAYERS` + `TEAMS` + `PLAYER_TEAMS` → zweryfikować `--player <id> --dry-run` | nowy wiersz w `players` + statystyki od pierwszego syncu |
| **Odeszły** (powrót do Ekstraklasy, koniec kariery, koniec śledzenia) | usunąć ze słowników | sync przestaje śledzić; **dane historyczne zostają w bazie** (archiwum działa) |

#### 8.2.4 Bezpieczeństwo procedury

- Stary sezon (2025/26) fizycznie nietknięty: `UNIQUE(player_id, season)` w `player_stats` i `player_stats_by_competition` → nowe wiersze zamiast nadpisywania.
- Żadna operacja nie usuwa danych — worst case = zmarnowane wywołania API.
- Każdy nowy/zmieniony zawodnik przechodzi indywidualny `--dry-run` przed pełnym synciem.

### 8.3 Zmiana zakresu backfillu (Sekcja 5)

Backfill nie cofa się do 2025/26 — obejmuje **wyłącznie sezon 2026/27 od jego początku (sierpień 2026) do dnia uruchomienia**. Szacunek kosztu: ~4–6 kolejek × liczba drużyn × ~1–2 wywołania na mecz ≈ **100–200 wywołań** (dokładnie z dry-runu). Snapshot kontrolny (Sekcja 5, krok 1) dotyczy tylko wierszy sezonu 2026/27.

**Guard starego sezonu (zaimplementowany 24.09.2026):** `is_in_current_season(match_date, season)` w `sync_full.py` — mecze z datą przed startem sezonu (1 sierpnia, z `season_start_date()`) są pomijane w każdym trybie, **włącznie z `--full`** (gdzie ochrona `synced_matches` jest celowo wyłączona). Mecz bez daty (`None` — nazwa pola API do weryfikacji, Sekcja 3B) jest przepuszczany z warningiem, żeby filtr nie zablokował syncu przy złej nazwie pola. Warning w logu informuje o liczbie odrzuconych starych meczów.
