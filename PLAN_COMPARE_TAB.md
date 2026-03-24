# Plan: Compare Tab Implementation

## Overview
Funkcjonalność porównywania dwóch piłkarzy w zakładce "Compare" z wykresem radarowym, bar chart i tabelą.

## Decyzje projektowe

| Aspekt | Decyzja |
|--------|---------|
| Wybór piłkarzy | 2 dropdowny (Player 1, Player 2) z pozycją |
| Limit | 2 piłkarzy |
| Selektywne stats | Checkboxes do wyboru stats do porównania |
| Wizualizacja | Radar chart + Bar chart + Tabela |
| Sezony | Ten sam dla obu (1 selector) |
| Pozycje | Pole vs Pole, GK vs GK |
| Premium | Na razie wszystko darmowe |
| Stats | Obecne + plan rozszerzenia (xG, xA) |

## UI Layout (wg screenshotów)

### Field Players UI
```
┌─────────────────────────────────────────────────────────────────┐
│  ⚖️ Compare Polish Football Players Abroad                     │
│  Detailed League Statistics Comparison                          │
├──────────────────────────┬──────────────────────────────────────┤
│  Select first player ▼   │  Select second player ▼             │
│  Robert Lewandowski (FW) │  Matty Cash (DEF)                   │
├──────────────────────────┴──────────────────────────────────────┤
│  📅 Comparing current season: 2025-26                           │
│  🌍 Comparing field players                                     │
├─────────────────────────────────────────────────────────────────┤
│  Select statistics to compare                                   │
│                                                                 │
│  OFFENSE           │  DEFENSE        │  GENERAL                │
│  ☑ Goals           │  ☐ Yellow Cards │  ☑ Matches Played      │
│  ☑ Assists         │  ☐ Red Cards    │  ☑ Games Started       │
│  ☑ G/90            │                 │  ☐ Minutes Played      │
│  ☑ A/90            │                 │                         │
│  ☑ G+A/90          │                 │                         │
├─────────────────────────────────────────────────────────────────┤
│  [Compare Players]                                              │
├─────────────────────────────────────────────────────────────────┤
│  Comparison: Robert Lewandowski vs Matty Cash                   │
│                                                                 │
│  📊 RADAR CHART (normalizowane 0-100)                          │
│  📊 BAR CHART (side-by-side bars)                              │
│  📋 TABLE (Stat | Player1 | Player2)                           │
└─────────────────────────────────────────────────────────────────┘
```

### Goalkeepers UI
```
┌─────────────────────────────────────────────────────────────────┐
│  ⚖️ Compare Polish Football Players Abroad                     │
├──────────────────────────┬──────────────────────────────────────┤
│  Łukasz Skorupski (GK)   │  Radosław Majecki (GK)              │
├──────────────────────────┴──────────────────────────────────────┤
│  📅 Comparing current season: 2025-26                           │
│  🧤 Comparing goalkeepers                                       │
├─────────────────────────────────────────────────────────────────┤
│  Select statistics to compare                                   │
│                                                                 │
│  GOALKEEPER STATS   │  PENALTIES      │  GENERAL               │
│  ☑ Saves            │  ☑ Saved        │  ☑ Matches             │
│  ☑ Save %           │  ☑ Allowed      │  ☑ Starts              │
│  ☑ Clean Sheets     │                 │  ☑ Minutes             │
│  ☑ Clean Sheet %    │                 │                        │
│  ☑ Goals Against    │                 │                        │
│  ☑ GA/90            │                 │                        │
│  ☑ Shots on Target  │                 │                        │
├─────────────────────────────────────────────────────────────────┤
│  [Compare Players]                                              │
└─────────────────────────────────────────────────────────────────┘
```

## Stats Definitions

### Field Players (obecnie dostępne)
| Stat | Opis | Dostępne |
|------|------|----------|
| Goals | Gole | ✅ |
| Assists | Asysty | ✅ |
| G/90 | Gole per 90 minut | ✅ |
| A/90 | Asysty per 90 minut | ✅ |
| G+A/90 | Gole + Asysty per 90 min | ✅ (obliczane) |
| Yellow Cards | Żółte kartki | ✅ |
| Red Cards | Czerwone kartki | ✅ |
| Matches Played | Mecze rozegrane | ✅ |
| Games Started | Mecze w pierwszym składzie | ✅ |
| Minutes Played | Minuty na boisku | ✅ |

### Goalkeepers (obecnie dostępne)
| Stat | Opis | W bazie |
|------|------|---------|
| Saves | Paradowania | ✅ |
| Save % | % obronionych strzałów | ✅ |
| Clean Sheets | Mecze bez straconej bramki | ✅ |
| Clean Sheet % | % meczów bez bramki | ✅ |
| Goals Against | Stracone gole | ✅ |
| GA/90 | Gole stracone / 90 min | ✅ |
| Shots on Target | Strzały celne na bramkę | ✅ |
| Penalties Saved | Rzuty karne obronione | ✅ |
| Penalties Allowed | Rzuty karne stracone | ✅ |
| Matches | Mecze rozegrane | ✅ |
| Starts | Mecze w składzie | ✅ |
| Minutes | Minuty na boisku | ✅ |

## Implementation Steps

### Krok 1: UI Player Selection
- 2 selectboxy z autocomplete
- Format: "Name (Position)" - np. "Robert Lewandowski (FW)", "Łukasz Skorupski (GK)"
- Info bar z sezonem i typem graczy

### Krok 2: Stats Selection Checkboxes
- Dynamiczne checkboxy zależne od typu (field vs GK)
- Domyślnie zaznaczone główne stats
- Grupy w kolumnach (st.columns)

### Krok 3: Compare Button
- Walidacja: obaj gracze wybrani, różni gracze, kompatybilne pozycje
- Fetch stats dla obu

### Krok 4: Radar Chart (Plotly)
- Normalizacja: `(value / max_of_both) * 100`
- 2 poligony (różne kolory)
- Kategorie zależne od wybranych checkboxów

### Krok 5: Bar Chart (Plotly)
- Side-by-side bars
- Kategorie na X, wartości na Y

### Krok 6: Table
- Stat | Player 1 | Player 2
- Zielony highlight dla lepszej wartości

## Phase 3: Future - Rozszerzone statystyki

### 3.1 Dodanie do bazy (PlayerStats model)
```python
# Extended field player stats
shots: Mapped[int] = mapped_column(Integer, default=0)
shots_on_target: Mapped[int] = mapped_column(Integer, default=0)
dribbles_attempted: Mapped[int] = mapped_column(Integer, default=0)
dribbles_successful: Mapped[int] = mapped_column(Integer, default=0)
passes: Mapped[int] = mapped_column(Integer, default=0)
passes_accuracy: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
key_passes: Mapped[int] = mapped_column(Integer, default=0)
xg: Mapped[float] = mapped_column(Numeric(5, 2), default=0)  # expected goals
xa: Mapped[float] = mapped_column(Numeric(5, 2), default=0)  # expected assists

# Extended GK stats
crosses_stopped: Mapped[int] = mapped_column(Integer, default=0)
punches: Mapped[int] = mapped_column(Integer, default=0)
runs_out: Mapped[int] = mapped_column(Integer, default=0)
```

### 3.2 Aktualizacja sync_full.py
- Sprawdzić czy RapidAPI zwraca te dane
- Dodać mapowanie w `parse_player_stats()`

## Zadania do wykonania

### MVP (teraz):
- [x] Dodać helper `is_gk(player)` - sprawdza position == "GK"
- [x] Dodać `display_radar_chart(p1_stats, p2_stats, is_gk)` - Plotly radar
- [x] Dodać `display_comparison_table(p1_stats, p2_stats, is_gk)` - HTML table
- [x] Zaimplementować logikę w tab3
- [x] Walidacja pozycji (GK vs GK, Field vs Field)
- [x] Stylowanie tabeli (zielony dla lepszych wartości)

### Future:
- ❌ NIE PLANOWANE - xG, xA, shots, passes nie są potrzebne

## Status: ✅ UKOŃCZONE
