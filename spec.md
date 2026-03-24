# Specyfikacja Architektoniczna: StationTester Pro (TUI) - Wersja 4.0

Jesteś zaawansowanym agentem programistycznym (Senior Python/PowerShell Developer). Twoim zadaniem jest stworzenie profesjonalnej aplikacji TUI we frameworku Textual do zdalnego testowania stanowisk Windows. Ta specyfikacja ma charakter wykonawczy. Traktuj ją jako kontrakt techniczny, a nie luźną wizję produktu.

## 1. Cel i Założenia Nadrzędne
- Aplikacja służy do uruchamiania paczek testów diagnostycznych na zdalnych stanowiskach Windows przez WinRM.
- Architektura musi rozdzielać:
  - warstwę sterowania i UI: Python + Textual,
  - warstwę wykonawczą na hostach: skrypty PowerShell `.ps1`.
- Aplikacja musi być rozwijalna przez dokładanie nowych skryptów i manifestów bez przebudowy całego systemu.
- System musi być bezpieczny operacyjnie, odporny na błędy infrastruktury i czytelny w diagnozie problemów.

## 2. Wymagania Niefunkcjonalne
- UI nie może blokować się dłużej niż 100 ms podczas aktywnego wykonywania testów.
- Wszystkie operacje zdalne muszą być wykonywane asynchronicznie lub delegowane poza główną pętlę zdarzeń `asyncio`.
- Każdy test musi mieć jawnie zdefiniowany timeout.
- Każdy błąd musi zostać zmapowany na zdefiniowany status domenowy.
- Każdy zapis raportu i audit logu musi być atomowy.
- Logi aplikacyjne muszą być strukturyzowane i zawierać `run_id` oraz `correlation_id`.
- Wszystkie pliki tekstowe systemu muszą używać kodowania UTF-8:
  - specyfikacje,
  - YAML,
  - JSON,
  - logi,
  - raporty HTML/CSV,
  - `stdout` i `stderr` skryptów PowerShell.

## 3. Architektura Systemu i Asynchroniczność
- **Aplikacja główna:** Python + Textual, uruchamiana centralnie na serwerze lub stacji operatorskiej.
- **Eksekutory:** skrypty PowerShell `.ps1`, uruchamiane na stanowiskach w tle przez WinRM bez interakcji z użytkownikiem końcowym.
- **Asynchroniczność:** warstwa UI i orkiestracji działa w `asyncio`. Wywołania WinRM nie mogą blokować interfejsu. Dopuszczalne jest użycie `asyncio.to_thread` dla bibliotek synchronicznych lub osobnej warstwy executorów.
- **Separacja odpowiedzialności:**
  - moduł konfiguracji,
  - moduł walidacji,
  - moduł komunikacji WinRM,
  - moduł orkiestracji testów,
  - moduł raportowania,
  - moduł audit logu,
  - moduł UI.

## 4. Model Wykonywania Testów
- Testy w ramach jednej paczki są domyślnie wykonywane sekwencyjnie.
- Definicja paczki może oznaczyć grupę testów jako `parallel_group`. Tylko testy w tej samej grupie mogą być uruchamiane równolegle.
- W jednej paczce nie wolno równolegle uruchamiać testów, które deklarują konflikt zasobów, np. ten sam proces, ten sam interfejs lub ten sam ekran.
- Aplikacja może wykonywać paczki równolegle maksymalnie na `N` stanowiskach jednocześnie. `N` musi być konfigurowalne, a wartość domyślna wynosi 3.
- Jedno stanowisko nie może być testowane przez więcej niż jedną aktywną paczkę jednocześnie.
- Dla każdego testu muszą istnieć pola:
  - `timeout_seconds`,
  - `retry_count`,
  - `retry_backoff_seconds`,
  - `continue_on_fail`,
  - `severity`,
  - `tags`.
- Po niepowodzeniu testu system stosuje politykę:
  - jeśli `continue_on_fail=true`, paczka przechodzi do kolejnego testu,
  - jeśli `continue_on_fail=false`, paczka kończy wykonywanie nowych testów w trybie fail-fast.
- Retry dotyczy tylko błędów przejściowych infrastruktury, nie błędów logicznych testu.
- Każdy test musi deklarować `resource_locks`, które pozwalają orkiestratorowi blokować równoległe uruchomienie testów używających tego samego zasobu.

### 4.1. Maszyna Stanów Runu i Testu
Dozwolone stany techniczne runu:
- `QUEUED`
- `PRECHECK_RUNNING`
- `WAITING_FOR_OPERATOR_CONFIRMATION`
- `READY`
- `RUNNING`
- `CANCELLATION_REQUESTED`
- `CANCELLING`
- `FINISHED`
- `FAILED_TO_START`

Dozwolone stany techniczne testu:
- `PENDING`
- `RUNNING`
- `RETRY_SCHEDULED`
- `FINISHED`
- `CANCELLED_TECHNICAL`
- `FAILED_TO_START`

Wymagania:
- Run i test muszą przechodzić tylko przez jawnie zdefiniowane przejścia stanów.
- Stan techniczny służy do orkiestracji i obserwowalności; nie zastępuje domenowego `status`.
- Po restarcie aplikacji system musi umieć odtworzyć stan `QUEUED`, `RUNNING`, `CANCELLING` oraz rozpoznać runy osierocone.
- Run osierocony po restarcie musi zostać oznaczony jako wymagający rekonsyliacji i nie może automatycznie uruchamiać nowych testów bez sprawdzenia stanu.

## 5. Model Statusów Domenowych
Dozwolone statusy testu i paczki:
- `PASS`
- `FAIL`
- `SKIPPED`
- `ERROR`
- `TIMEOUT`
- `ABORTED`
- `AUTH_FAILED`
- `UNREACHABLE`
- `INVALID_OUTPUT`

Dozwolone `termination_reason` dla paczki:
- `COMPLETED`
- `FAIL_FAST`
- `OPERATOR_CANCEL`
- `PRECHECK_REJECTED`
- `STARTUP_ERROR`
- `INFRASTRUCTURE_ERROR`
- `RECOVERY_AFTER_RESTART`

Zasady interpretacji:
- `PASS`: test spełnił kryterium.
- `FAIL`: test wykonał się poprawnie, ale warunek biznesowy nie został spełniony.
- `SKIPPED`: test został pominięty zgodnie z warunkiem uruchomienia lub polityką.
- `ERROR`: błąd wykonania skryptu lub logiki po stronie aplikacji.
- `TIMEOUT`: przekroczono limit czasu połączenia lub wykonania.
- `ABORTED`: wykonanie zatrzymane przez operatora lub politykę orchestration.
- `AUTH_FAILED`: błąd autoryzacji, np. 401, Kerberos failure, brak uprawnień.
- `UNREACHABLE`: host nieosiągalny, WinRM niedostępny, błąd sieci.
- `INVALID_OUTPUT`: skrypt zwrócił niepoprawny JSON lub dane niezgodne ze schematem.

Zasady dla paczki:
- `final_status` oznacza domenowy wynik końcowy paczki.
- `termination_reason` opisuje dlaczego wykonywanie paczki zakończyło się w danym miejscu.
- Anulowanie przez operatora zawsze daje `final_status=ABORTED` oraz `termination_reason=OPERATOR_CANCEL`.
- Fail-fast po błędzie testu nie może być raportowany jako anulowanie operatora. Jeśli ostatni test zwrócił `FAIL`, paczka kończy się jako `final_status=FAIL` oraz `termination_reason=FAIL_FAST`.
- Odrzucenie startu przez operatora po ostrzeżeniu pre-flight nie tworzy pełnego runu paczki, ale musi zostać zapisane w audycie jako `PRECHECK_REJECTED`.
- Problem startowy przed uruchomieniem pierwszego testu musi skutkować `final_status=ERROR` albo `UNREACHABLE`, zależnie od klasy błędu, oraz odpowiednim `termination_reason`.

## 6. Pre-flight Check i Ochrona Stanowiska
Przed uruchomieniem paczki system musi wykonać pre-flight check:
1. Lekki skrypt sprawdza użycie CPU, użycie RAM, dostępność WinRM, podstawową responsywność hosta oraz zgodność z warunkami startu.
2. Jeśli CPU > 80% lub RAM usage > 90%, start paczki ma zostać zablokowany warunkowo.
3. UI musi wyświetlić modal z komunikatem: `UWAGA: Stanowisko jest mocno obciążone (CPU: X%, RAM: Y%). Czy na pewno chcesz uruchomić testy?`
4. Modal musi mieć przyciski `[TAK]` i `[NIE]`.
5. Wybór `[TAK]` oznacza `forced_after_preflight_warning=true` i musi zostać zapisany w audycie.
6. Wybór `[NIE]` kończy próbę uruchomienia bez tworzenia pełnego runu paczki.

## 7. Anulowanie i Panic Button
- Kliknięcie `[ANULUJ]` ustawia flagę `cancellation_requested=true`.
- Od momentu ustawienia tej flagi żadne nowe testy ani nowe grupy równoległe nie mogą wystartować.
- Aktualnie wykonywany test:
  - może zostać dokończony, jeśli nie da się go bezpiecznie przerwać,
  - albo może zostać zakończony przez kontrolowany timeout/cancel po stronie Pythona.
- Jeśli biblioteka WinRM nie pozwala bezpiecznie przerwać komendy, aplikacja musi oznaczyć zadanie jako `ABORTED_PENDING_REMOTE_FINISH` wewnętrznie, ale do raportu domenowego zapisać `ABORTED`.
- Po anulowaniu połączenie WinRM powinno zostać zamknięte lub zwolnione zgodnie z polityką cleanup.
- Końcowy status paczki po anulowaniu to `ABORTED`.
- Akcja anulowania musi zostać zapisana w audit logu z operatorem i timestampem.

## 8. Timeouty, Retry i Odporność na Niestabilną Sieć
- Muszą istnieć osobne timeouty:
  - `connect_timeout_seconds`,
  - `execution_timeout_seconds`,
  - `json_parse_timeout_seconds` jeśli parser działa z limitem czasu.
- System musi wspierać retry dla:
  - zestawienia połączenia WinRM,
  - błędów sieciowych o charakterze transient,
  - chwilowych błędów transportowych.
- Retry nie może być stosowane dla:
  - `AUTH_FAILED`,
  - błędów walidacji danych,
  - logicznego `FAIL` testu.
- Backoff musi być konfigurowalny. Minimalnie wspierany jest `fixed` i `exponential`.
- System musi rozróżniać błędy transient i permanent.
- UI musi umożliwiać:
  - ponowienie pojedynczego testu,
  - ponowienie całej paczki,
  - `re-run failed only`,
  - `re-run error only`.
- Retry musi być idempotentne na poziomie orkiestratora:
  - ta sama próba nie może zostać zarejestrowana dwa razy,
  - każda próba musi mieć `attempt_no`,
  - raport końcowy musi pokazywać liczbę prób.

## 9. Kontrakt Komunikacyjny Python <-> PowerShell
- Każdy skrypt `.ps1` przyjmuje parametry wejściowe zgodnie z własnym manifestem.
- Każdy skrypt musi zwrócić dokładnie jeden obiekt JSON na `stdout`.
- Zabronione jest mieszanie logów tekstowych z JSON-em na `stdout`. Diagnostyka pomocnicza może trafiać na `stderr`, ale nie może psuć parsowania.
- Skrypt musi kończyć się kontrolowanym `exit_code`:
  - `0` dla poprawnego wykonania logiki skryptu niezależnie od tego, czy wynik domenowy to `PASS` czy `FAIL`,
  - różnym od `0` tylko dla błędu wykonania skryptu lub środowiska uruchomieniowego.
- `stdout` i `stderr` muszą być kodowane w UTF-8.
- System musi definiować maksymalny rozmiar bufora `stdout` i `stderr`; jego przekroczenie musi zostać zmapowane na `INVALID_OUTPUT` albo `ERROR` zgodnie z klasą problemu.
- Skrypt nie może emitować artefaktów binarnych na `stdout`. Artefakty muszą być zapisane jako pliki i zwrócone przez JSON jako ścieżki lub metadane artefaktów.
- Minimalny kontrakt wyniku testu:

```json
{
  "test_name": "disk_free_space",
  "status": "PASS",
  "message": "Wolne miejsce spelnia wymagania",
  "value": "52.3 GB",
  "timestamp_utc": "2026-03-23T10:15:30Z",
  "duration_ms": 842,
  "error_code": null,
  "severity": "INFO",
  "details": {
    "disk": "C:",
    "free_gb": 52.3,
    "threshold_gb": 20
  },
  "host_info": {
    "hostname": "ST01",
    "ip": "192.168.1.15"
  },
  "script_version": "1.0.0",
  "attempt_no": 1,
  "artifacts": []
}
```

Wymagania:
- `status` musi należeć do modelu statusów domenowych.
- `timestamp_utc` musi być w ISO 8601 UTC.
- `duration_ms` musi być liczbą całkowitą >= 0.
- `error_code` musi być `null` lub kodem kontrolowanym przez aplikację/skrypt.
- `severity` musi przyjmować wartości `CRITICAL`, `WARNING` albo `INFO`.
- `details` musi być obiektem JSON z dodatkowymi danymi diagnostycznymi.
- `script_version` jest obowiązkowe.
- `attempt_no` musi być liczbą całkowitą >= 1.
- `artifacts` musi być tablicą metadanych artefaktów i może być puste.
- Jeśli `exit_code != 0`, a JSON nie został zwrócony, wynik musi zostać zmapowany na `ERROR`, `TIMEOUT`, `AUTH_FAILED` albo `UNREACHABLE` według mappera błędów.

Jeśli JSON jest niepoprawny lub niezgodny ze schematem, wynik musi zostać oznaczony jako `INVALID_OUTPUT`.

## 10. Rozróżnienie Błędu Testu i Błędu Infrastruktury
- Zbyt mało miejsca na dysku to `FAIL`.
- Brak odpowiedzi WinRM to `UNREACHABLE`.
- Błąd autoryzacji to `AUTH_FAILED`.
- Wyjątek po stronie skryptu to `ERROR`.
- Niepoprawny JSON to `INVALID_OUTPUT`.
- Timeout połączenia lub wykonania to `TIMEOUT`.

Implementacja musi jawnie mapować klasy wyjątków na statusy domenowe. Niedopuszczalne jest wrzucanie wszystkich błędów do wspólnego `FAIL`.

## 11. Konfiguracja, Schematy i Walidacja YAML
Struktura katalogów:
- `/configs/stations.yaml` - baza stanowisk.
- `/configs/packages.yaml` - definicje paczek.
- `/scripts/` - skrypty `.ps1` i manifesty testów.
- `/reports/` - raporty JSON, CSV i HTML.
- `/audit/` - dziennik działań operatora.
- `/tests/` - testy `pytest`.

Wymagania walidacyjne:
- Każdy plik YAML musi zostać zwalidowany przed zapisem i przed uruchomieniem.
- Błędna konfiguracja nie może zostać uruchomiona.
- UI musi pokazywać dokładny błąd walidacji z nazwą pola.
- Walidacja musi obejmować:
  - zgodność ze schematem,
  - unikalność `station_id`,
  - poprawność adresu IP lub hostname,
  - istnienie wskazanych plików skryptów,
  - poprawność referencji paczka -> skrypt,
  - poprawność typów parametrów,
  - zgodność wersji schematu.
- Konfiguracja musi mieć pole `schema_version`.
- System ma wspierać migracje starszych wersji configu.
- Migracja configu musi być jawna, wersjonowana i odwracalna na poziomie backupu pliku wejściowego.
- Rekomendowane narzędzia: `pydantic` lub `jsonschema`.

Wymagania kompatybilności wersji:
- Każdy config i manifest musi deklarować własny `schema_version`.
- Aplikacja musi deklarować wspierany zakres wersji schematu.
- Jeśli wersja configu lub manifestu jest nowsza niż wspierana przez aplikację, system nie może uruchomić testów i musi zgłosić precyzyjny błąd kompatybilności.
- Jeśli wersja jest starsza, system może:
  - uruchomić migrację,
  - albo odmówić startu z informacją, że migracja jest wymagana.

## 12. Manifesty Skryptów i Standaryzacja Parametrów
Każdy skrypt testowy musi mieć manifest opisujący metadane i parametry. Manifest może być YAML lub JSON.

Minimalna struktura manifestu:

```yaml
name: disk_free_space
version: 1.0.0
schema_version: 1.0.0
min_app_version: 1.0.0
description: Sprawdza wolne miejsce na dysku
tags:
  - system
  - storage
severity: WARNING
supports_parallel: true
parameters:
  - name: disk_letter
    type: string
    required: true
  - name: min_free_gb
    type: int
    required: true
conditions:
  - type: disk_exists
    parameter: disk_letter
```

Wymagania:
- Każdy parametr musi mieć typ, informację `required/optional`, opcjonalny `default` i opis.
- UI powinno generować formularz dynamicznie na podstawie manifestu.
- Ten sam skrypt musi dać się wykorzystać w wielu paczkach z różnymi parametrami.
- Manifesty muszą być wersjonowane i walidowane.
- Manifest musi jawnie wskazywać:
  - nazwę pliku skryptu,
  - wersję schematu manifestu,
  - minimalną wersję aplikacji wymaganą do obsługi manifestu.
- Niekompatybilny manifest nie może zostać załadowany do katalogu testów aktywnych.

## 13. Tagi, Ważność i Warunki Uruchamiania
- Każdy test musi wspierać tagi, np.:
  - `hardware`,
  - `network`,
  - `display`,
  - `system`,
  - `security`,
  - `performance`.
- Każdy test musi mieć poziom ważności:
  - `CRITICAL`,
  - `WARNING`,
  - `INFO`.
- Definicja paczki może zawierać warunki uruchomienia testu, np.:
  - uruchom test monitora tylko jeśli aktywna jest sesja użytkownika,
  - uruchom test procesu tylko dla określonego typu stanowiska,
  - uruchom test dysku tylko jeśli dysk istnieje.
- Niespełniony warunek uruchomienia kończy test statusem `SKIPPED` z jawnym powodem.

## 14. Bezpieczeństwo i Poświadczenia
- Dane dostępowe nie mogą być przechowywane jawnie w `stations.yaml`, `packages.yaml` ani innych plikach konfiguracyjnych.
- Sekrety muszą być pobierane z bezpiecznego magazynu, np.:
  - Windows Credential Manager,
  - DPAPI,
  - Vault,
  - zmienne środowiskowe jako wariant awaryjny.
- Obsługiwane mechanizmy auth muszą być jawnie zdefiniowane. Minimalnie:
  - Kerberos,
  - NTLM.
- Jeśli wspierany jest `CredSSP`, musi być wyraźnie oznaczony jako opcjonalny i podlegać polityce bezpieczeństwa.
- Logi, raporty i błędy UI nie mogą zawierać haseł, tokenów, pełnych connection stringów ani innych sekretów.
- Dane wrażliwe muszą być maskowane.

## 15. Raportowanie i Historia
System musi generować raport końcowy dla każdego wykonania paczki.

Minimalna struktura raportu zbiorczego:

```json
{
  "run_id": "2026-03-23_10-20-15_ST01_pkg_basic",
  "correlation_id": "6d4b1b22-90f3-4c33-8a0c-6eb6e4032d11",
  "station_id": "ST01",
  "station_name": "Stanowisko 01",
  "package_name": "basic_healthcheck",
  "operator": "DOMAIN\\operator1",
  "config_version": "1.2.0",
  "started_at_utc": "2026-03-23T10:20:15Z",
  "finished_at_utc": "2026-03-23T10:21:44Z",
  "duration_ms": 89000,
  "final_status": "FAIL",
  "termination_reason": "FAIL_FAST",
  "forced_after_preflight_warning": false,
  "environment_snapshot": {
    "hostname": "ST01",
    "os_version": "Windows 11 Pro",
    "uptime_seconds": 45200,
    "ip_addresses": ["192.168.1.15"]
  },
  "results": [],
  "summary": {
    "passed": 5,
      "failed": 1,
      "skipped": 0,
      "errors": 1,
      "timeouts": 0
    },
  "event_log": [],
  "attempt_summary": {
    "total_attempts": 8,
    "retried_tests": 2
  }
}
```

Wymagania:
- Raport musi zawierać wszystkie wyniki testów.
- Raport musi zawierać końcowy status paczki.
- Raport musi zawierać `termination_reason`.
- Raport musi zawierać informację, czy operator wymusił start mimo ostrzeżenia pre-flight.
- Raport musi zawierać snapshot środowiska stanowiska.
- Raport musi zawierać informację o próbach wykonania testów i retry.
- Historia raportów musi dać się filtrować po:
  - stanowisku,
  - paczce,
  - operatorze,
  - statusie końcowym,
  - zakresie czasu.
- System musi wspierać eksport raportów do:
  - JSON,
  - CSV,
  - HTML.

## 16. Audit Log Operatora
System musi prowadzić osobny audit log działań operatora.

Audit musi zapisywać:
- kto uruchomił test,
- kiedy,
- na jakim stanowisku,
- jaką paczkę,
- kto wymusił start mimo ostrzeżenia pre-flight,
- kto anulował wykonanie,
- kto wykonał `re-run failed only`,
- kto zmodyfikował konfigurację stanowisk lub paczek.

Każdy wpis audytu musi zawierać co najmniej:
- `audit_id`,
- `timestamp_utc`,
- `operator`,
- `action`,
- `target_type`,
- `target_id`,
- `run_id` jeśli dotyczy,
- `details`.

## 17. Kolejkowanie i Współbieżność Operatorów
- System musi posiadać kolejkę uruchomień paczek.
- Jeśli stanowisko jest już zajęte, UI ma pokazać status `stanowisko zajete` i zablokować równoległy start drugiej paczki na tym samym hoście.
- Kolejka musi zachować kolejność FIFO, chyba że później zostanie jawnie dodany priorytet.
- Informacja o stanie kolejki musi być widoczna w UI.
- Stan kolejki i aktywnych runów musi być trwale zapisany, tak aby restart aplikacji nie powodował utraty informacji o runach oczekujących i uruchomionych.

## 18. Tryb Dry-Run
System musi wspierać tryb `dry-run`, który:
- waliduje konfigurację,
- sprawdza dostępność WinRM,
- sprawdza obecność i zgodność skryptów,
- pokazuje plan wykonywania,
- niczego faktycznie nie uruchamia na stanowisku.

## 19. Plugin System i Wykrywanie Testów
- System powinien wspierać model `script + manifest`.
- Dostępne testy powinny być wykrywane automatycznie na podstawie manifestów w `/scripts/`.
- Zgodność manifestu musi być walidowana podczas startu aplikacji.
- Wersje skryptów i manifestów muszą być pokazywane w UI oraz zapisywane w raporcie.

## 20. Interfejs Użytkownika (TUI)
Zakładki minimalne:
1. **Dashboard**
   - wybór stanowiska i paczki,
   - duży przycisk `[START]`,
   - przycisk `[ANULUJ]`,
   - panel logów w czasie rzeczywistym,
   - status kolejki i status wykonywania.
2. **Stanowiska**
   - CRUD dla `stations.yaml`,
   - walidacja inline.
3. **Paczki**
   - CRUD dla `packages.yaml`,
   - dynamiczne formularze parametrów na podstawie manifestów.
4. **Skrypty**
   - podgląd skryptów `.ps1`,
   - podgląd manifestów,
   - wersje skryptów.
5. **Historia**
   - przeglądarka raportów,
   - filtrowanie,
   - porównywanie raportów.
6. **Audyt**
   - przeglądarka działań operatorów.

## 21. Wymagane Skrypty PowerShell
Zbuduj skrypty `.ps1` dla:
1. Pre-flight check: CPU, RAM, podstawowa dostępność hosta i WinRM.
2. Liczby monitorów i głównego ekranu.
3. Podłączonej myszki i klawiatury.
4. Działania wskazanego procesu.
5. Wolnego miejsca na wskazanym dysku.
6. Pingu do wskazanego adresu IP.
7. Rozdzielczości ekranu.
8. Zrzutu krytycznych błędów z Event Viewera z ostatnich 24h.
9. Snapshotu środowiska: hostname, użytkownik, OS version, uptime, model urządzenia, adresy IP, ostatni restart.

## 22. Observability i Logowanie
- Logi muszą być strukturyzowane.
- Każdy wpis logu musi zawierać:
  - `timestamp_utc`,
  - `level`,
  - `run_id`,
  - `correlation_id`,
  - `station_id`,
  - `event_type`,
  - `message`.
- Dla każdego testu należy logować:
  - start,
  - koniec,
  - czas trwania,
  - decyzję retry,
  - mapowanie błędu na status domenowy.

## 23. Quality Assurance i Testy
- Projekt musi posiadać testy jednostkowe `pytest` dla:
  - parserów YAML,
  - walidatorów schematów,
  - parsera JSON ze skryptów,
  - generatora raportów,
  - mappera błędów domenowych,
  - modułu retry i cancel,
  - mockowania połączeń WinRM.
- Skrypty i moduły bez testów są traktowane jako niekompletne.
- Każdy bugfix dotyczący parsera, raportowania, cancel lub statusów musi mieć test regresyjny.

## 24. Środowisko Testowe
- Adres IP stanowiska testowego: `10.122.7.119`
- Agent ma weryfikować warstwę komunikacji WinRM na powyższym adresie, ale implementacja musi umożliwiać pełne testy lokalne z mockami bez zależności od żywego hosta.

## 25. Kolejność Realizacji
1. Zaimplementuj schematy i walidację konfiguracji.
2. Zaimplementuj manifesty skryptów i loader pluginów.
3. Zaimplementuj moduł WinRM z timeoutami, retry i mapowaniem błędów domenowych.
4. Zaimplementuj pre-flight check i politykę wymuszonego startu.
5. Zaimplementuj orkiestrator paczek, kolejkę i cancel behavior.
6. Zaimplementuj raportowanie, eksport i audit log.
7. Zbuduj TUI i połącz je z orkiestratorem.
8. Dodaj historię, porównywanie raportów i akcje re-run.
