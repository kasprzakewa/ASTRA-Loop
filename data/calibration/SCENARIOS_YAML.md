# Przewodnik po `scenarios.yaml`

Ten plik opisuje, jak pisać scenariusze kalibracji PD w YAML. Jeden plik (`data/calibration/scenarios.yaml`) obsługuje:

- GUI → **Calibrate…** (Run / Tune / Scenarios / Guides)
- `python scripts/validate_pd.py`
- `python scripts/tune_pd.py` (domyślne wartości, Monte Carlo)

Ścieżki w `flights[].csv` są **względem katalogu pliku YAML** (np. `../converted/astra_3d.csv`).

---

## Mental model

```
flights          = skąd bierzemy telemetrię boostu (CSV z OpenRocket)
sil_presets      = jak zachowuje się plant w fazie coast (wiatr, masa, Cd)
test_cases       = flight + sil  →  jeden uruchomiony eksperyment
suites           = lista test_cases do batch run
defaults         = wspólne ustawienia (PD, pluginy, targety, Monte Carlo)
sil_bounds       = zakresy losowania dla tune_pd.py (nie dla validate/GUI)
```

**Boost** = dane z CSV (do burnoutu).  
**Coast** = symulowany plant z parametrami z `sil_presets`.  
**PD** widzi tylko predykcję apogeii i porównuje z `mission_target_apogee_m`.

---

## Szablon minimalny

```yaml
version: 1

defaults:
  mission_target_apogee_m: 2500.0
  tuning_target_apogee_m: 2450.0   # tylko tune_pd.py
  filter: NoFilter
  predictor: ApogeePredict3D
  controller: PDController
  coast_solver: euler
  pd:
    kp: 0.08
    kd: 0.0005
    error_deadband: 10.0
    max_deploy_speed: 200.0
  monte_carlo:
    bounds_preset: monte_carlo
    seeds: 20

sil_presets:
  nominal:
    wind_speed: 0.0
    gust_strength: 0.0
    plant_mass_scale: 1.0
    plant_cd_scale: 1.0

sil_bounds:
  monte_carlo:
    wind_speed: [0.0, 6.0]
    gust_strength: [0.0, 2.0]
    plant_mass_scale: [0.97, 1.03]
    plant_cd_scale: [0.92, 1.08]

flights:
  - name: moj_lot
    csv: ../converted/moj_lot.csv
    description: Krótki opis

test_cases:
  - name: moj_lot_nominal
    flight: moj_lot
    sil: nominal
    description: Baseline

suites:
  smoke:
    description: Szybki test
    cases:
      - moj_lot_nominal
```

---

## Sekcja `defaults`

| Pole | Typ | Opis |
|------|-----|------|
| `mission_target_apogee_m` | float | **Cel misji** — setpoint PD w GUI, validate, firmware, `best_pd.json` |
| `tuning_target_apogee_m` | float | **Cel tuningu** — tylko grid search w `tune_pd.py`; zwykle niższy niż mission, żeby hamulce się włączyły |
| `filter` | string | Nazwa pluginu filtra, np. `NoFilter` |
| `predictor` | string | np. `ApogeePredict3D` |
| `controller` | string | np. `PDController` |
| `coast_solver` | string | `euler` (domyślnie) |
| `pd.kp`, `pd.kd`, `pd.error_deadband`, `pd.max_deploy_speed` | float | Domyślne gainy PD |
| `monte_carlo.bounds_preset` | string | Klucz w `sil_bounds` |
| `monte_carlo.seeds` | int | Liczba losowych prób SIL na kombinację PD w `tune_pd.py` |

### Mission vs tuning target

- **Mission (2500 m):** prawdziwy cel lotu.
- **Tuning (2450 m):** sztucznie obniżony cel na czas szukania `kp`/`kd`, bo przy 2500 m model open-loop (~2460 m) nie wymaga hamulców i wszystkie gainy wyglądają tak samo.

---

## Sekcja `sil_presets`

Presety **Coast SIL** — zaburzenia tylko na **planie** (plant), nie w predyktorze.

| Pole | Jednostka | Znaczenie |
|------|-----------|-----------|
| `wind_speed` | m/s | Stały wiatr poziomy na plant |
| `gust_strength` | m/s | Amplituda pionowych podmuchów |
| `plant_mass_scale` | × | Mnożnik masy plantu (1.03 = +3%) |
| `plant_cd_scale` | × | Mnożnik oporu plantu (1.08 = +8%) |
| `wind_seed` | int (opcjonalny) | Stały seed RNG wiatru; zwykle pomijany w YAML |

**Przykład — corner case „cięższy świat”:**

```yaml
sil_presets:
  mass_p5pct:
    wind_speed: 0.0
    gust_strength: 0.0
    plant_mass_scale: 1.05
    plant_cd_scale: 1.0
```

Nazwy presetów są dowolne; ważne, żeby `test_cases[].sil` na nie wskazywał.

---

## Sekcja `sil_bounds`

Używana **wyłącznie** przez `tune_pd.py` do losowania parametrów SIL w Monte Carlo.

```yaml
sil_bounds:
  monte_carlo:
    wind_speed: [0.0, 6.0]        # min, max
    gust_strength: [0.0, 2.0]
    plant_mass_scale: [0.97, 1.03]
    plant_cd_scale: [0.92, 1.08]
```

`defaults.monte_carlo.bounds_preset: monte_carlo` wybiera ten zestaw. Możesz mieć wiele presetów bounds, np. `conservative` i `aggressive`.

---

## Sekcja `flights`

Lista lotów boosterowych (CSV po konwersji z OpenRocket).

```yaml
flights:
  - name: astra_nominal          # unikalna nazwa (ID)
    csv: ../converted/astra_3d.csv
    description: Lot nominalny, apogeia OR ~2497 m
    optional: false                # domyślnie false
```

| Pole | Wymagane | Opis |
|------|----------|------|
| `name` | tak | Identyfikator używany w `test_cases.flight` |
| `csv` | tak | Ścieżka względna do YAML |
| `description` | nie | Opis dla człowieka |
| `optional` | nie | Jeśli `true` i brak pliku → test case może być pominięty |

### Dodawanie nowego lotu z OpenRocket

1. Eksport z OR: kolumny Time, Altitude, Vertical velocity, Lateral velocity.
2. Konwersja:
   ```bash
   python scripts/convert_openrocket_csv.py data/or/wiatr_5ms.csv \
     --profile apogee_3d -o data/converted/wiatr_5ms.csv
   ```
3. Wpis w `flights` + `test_cases` + ewentualnie `suites`.

---

## Sekcja `test_cases`

Jeden przypadek = **jeden CSV boost** + **jeden preset SIL**.

```yaml
test_cases:
  - name: astra_wind_6ms
    flight: astra_nominal      # musi istnieć w flights
    sil: wind_6ms              # musi istnieć w sil_presets (lub = nominal)
    description: Boost ASTRA, plant z wiatrem 6 m/s
    skip_if_missing: false     # domyślnie false
```

| Pole | Opis |
|------|------|
| `name` | Id używane w `suites.cases` |
| `flight` | Klucz z `flights` |
| `sil` | Klucz z `sil_presets` (domyślnie `nominal`) |
| `skip_if_missing` | Jeśli `true` i brak CSV → SKIP zamiast błędu |

**Kiedy `skip_if_missing: true`?**  
Gdy CSV jeszcze nie wyeksportowałeś z OR, ale chcesz mieć scenariusz „na przyszłość” w suite.

**Kiedy `flight.optional: true`?**  
Gdy sam lot jest opcjonalny — brak pliku też prowadzi do SKIP (jeśli `skip_if_missing` lub `optional`).

---

## Sekcja `suites`

Grupuje `test_cases` pod batch run.

```yaml
suites:
  validation:
    description: Pełna walidacja przed firmware
    cases:
      - astra_nominal
      - astra_wind_6ms
      - astra_mass_p3pct
```

- Nazwa suite (`validation`) → argument `--suite validation` w `validate_pd.py`.
- Kolejność w `cases` = kolejność uruchomień i wyników w GUI.
- Ten sam `test_case` może być w wielu suite'ach.

### Gotowe suite w repo

| Suite | Cel |
|-------|-----|
| `nominal_only` | Smoke — 2 idealne loty |
| `tuning_engagement` | Przypadki, gdzie hamulce powinny się włączyć |
| `validation` | Pełny zestaw (wiatr, masa, Cd, oba CSV) |

---

## Cookbook — typowe scenariusze

### 1. Ten sam boost, różne zaburzenia plantu

```yaml
test_cases:
  - name: nominal
    flight: astra_nominal
    sil: nominal
  - name: heavy_plant
    flight: astra_nominal
    sil: mass_p3pct
  - name: windy_plant
    flight: astra_nominal
    sil: wind_6ms
```

Jeden CSV, wiele warunków coast — to główny wzorzec testowania robustności PD.

### 2. Różne eksporty OR (wiatr w boost)

```yaml
flights:
  - name: or_wind
    csv: ../converted/astra_wind_px.csv
    optional: true

test_cases:
  - name: or_wind_nominal
    flight: or_wind
    sil: nominal
    skip_if_missing: true
```

Boost ma już wiatr z OR; coast plant = idealny (`nominal`).

### 3. Suite tylko pod tuning (szybki)

```yaml
suites:
  my_tune_check:
    description: Czy PD w ogóle hamuje
    cases:
      - astra_mass_p3pct
      - or_mass_p3pct
```

### 4. Suite pod regresję po zmianie fizyki

```yaml
suites:
  physics_regression:
    description: Po zmianie BODY_CROSS_SECTION lub Cd
    cases:
      - astra_nominal
      - or_nominal
```

Sprawdź **OR Apogee Error** — czy model nadal zgadza się z OpenRocket.

---

## Uruchamianie

### GUI

Open **Calibrate…** from the sidebar:

| Tab | Action |
|-----|--------|
| **Run** | Select suite and PD source → **Run Suite** → results table |
| **Tune** | **Run Tune** (quick or full) → **Apply best PD to GUI** |
| **Scenarios** | Edit and save `scenarios.yaml` |
| **Guides** | Read formatted docs (Scenarios scripting, Calibration workflow) |

Results: `data/calibration/results/gui_validation.json`. **Load selected CSV** loads a row into the main simulator.

### Terminal

```bash
# Wszystkie przypadki z suite
python scripts/validate_pd.py --suite validation

# Inny plik YAML
python scripts/validate_pd.py --scenarios data/calibration/scenarios.yaml --suite nominal_only

# Tuning (używa tuning_target, zapisuje mission_target do best_pd.json)
python scripts/tune_pd.py
python scripts/tune_pd.py --quick
```

---

## Czytanie wyników

Przykładowa linia:

```
astra_mass_p3pct           astra_nominal    mass_p3pct   target_err=   0.3m OR_err=  18.0m z=2500.3m
```

| Kolumna | Znaczenie |
|---------|-----------|
| `target_err` | \|osiągnięta apogeia − mission target\| |
| `OR_err` | \|osiągnięta apogeia − max(altitude z CSV OR)\| |
| `z` | Osiągnięta apogeia plantu |
| `SKIP` | Brak CSV lub nieznany case/flight |

**SKIP** nie jest błędem YAML — to świadome pominięcie opcjonalnego lotu.

---

## Walidacja składni

Po edycji w GUI (**Calibrate → Scenarios** → zapisz `scenarios.yaml`):

- sprawdzana jest składnia YAML,
- wywoływane jest `load_calibration_config()` — błąd = literówka w nazwie `flight`/`sil`/suite case.

Ręcznie:

```bash
python -c "from core.calibration_scenarios import load_calibration_config; \
  load_calibration_config('data/calibration/scenarios.yaml'); print('OK')"
```

---

## Częste błędy

| Problem | Przyczyna | Fix |
|---------|-----------|-----|
| `unknown flight 'foo'` | `test_cases.flight` nie ma w `flights` | Dodaj flight lub popraw nazwę |
| `unknown test case` w suite | Literówka w `suites.cases` | Nazwa musi = `test_cases[].name` |
| Wszystkie SKIP | Brak CSV, `optional`/`skip_if_missing` | Wyeksportuj CSV lub usuń z suite |
| PD nie hamuje przy mission 2500 | Open-loop < 2500 m | Normalne; testuj z `tuning_engagement` lub obniż target w GUI |
| `tune_pd` daje identyczne score | Tuning target za wysoki | Obniż `tuning_target_apogee_m` (np. 2440) |

---

## Konwencje nazewnictwa (zalecane)

```
flights:     <projekt>_<warunek>     → astra_nominal, or_wind_px
sil_presets: <typ>_<wartość>         → wind_6ms, mass_p3pct, cd_p8pct
test_cases:  <flight>_<sil>          → astra_nominal, astra_wind_6ms
suites:      <cel>                   → validation, nominal_only, tuning_engagement
```

---

## Powiązane pliki

- [`README.md`](README.md) — workflow kalibracji end-to-end
- [`scenarios.yaml`](scenarios.yaml) — aktywny manifest scenariuszy
- `core/calibration_scenarios.py` — parser i `run_suite()`
- `scripts/tune_pd.py` — Monte Carlo + grid PD
- `scripts/validate_pd.py` — batch walidacja suite
