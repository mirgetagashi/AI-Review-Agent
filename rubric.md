# Rubrika e vlerësimit

Ky është versioni për njerëz i `rubric.json`. **Numrat (pikët dhe brezat) janë
te `rubric.json`**; ky file shpjegon çfarë do të thotë secili nivel dhe çfarë
dëshmie pranohet. Nëse të dy nuk përputhen, vlen `rubric.json`.

Totali: **100 pikë**. Çdo kriter ka tre nivele:

- `missing`: mungon, gjithmonë 0 pikë
- `partial`: ekziston, por me mangësi të qarta
- `complete`: i plotë, me mangësi të vogla ose pa to

Pikët duhet të jenë brenda brezit të nivelit të zgjedhur. `score.py` refuzon
çdo raport ku niveli dhe pikët nuk përputhen.

---

## 1. Funksionaliteti (`functionality`), 20 pikë

A bën projekti atë që premton README ose detyra?

| Niveli | Pikë | Përshkrimi |
|---|---|---|
| missing | 0 | Nuk ekzekutohet fare ose nuk ka funksionalitet të dukshëm |
| partial | 8-15 | Ekzekutohet, por vetëm një pjesë e funksionalitetit punon |
| complete | 16-20 | Funksionaliteti kryesor punon në sandbox |

**Dëshmia:** komanda `bash scripts/sandbox-run.sh ...` me output dhe exit code;
file:rresht ku implementohet funksionaliteti.
**Kujdes:** sandbox-run me exit 2 ose 3 do të thotë "nuk mund ta ekzekutonim".
Kjo nuk është 0 pikë nga Reviewer-i, por `UNVERIFIABLE` nga Professor-i.

## 2. Struktura dhe arkitektura (`structure`), 15 pikë

| Niveli | Pikë | Përshkrimi |
|---|---|---|
| missing | 0 | Gjithçka në një file pa ndarje logjike |
| partial | 6-11 | Ka ndarje në module, por përgjegjësitë përzihen (p.sh. I/O brenda algoritmit) |
| complete | 12-15 | Module me përgjegjësi të qarta dhe varësi të arsyeshme |

**Dëshmia:** pema e folderëve (`find`, `ls`), file:rresht për problemet.

## 3. Kualiteti i kodit (`code_quality`), 15 pikë

| Niveli | Pikë | Përshkrimi |
|---|---|---|
| missing | 0 | Kod pothuajse i palexueshëm |
| partial | 6-11 | Lexueshëm, por me shumë gabime linti, duplikim ose funksione shumë të gjata |
| complete | 12-15 | Emërtim i qartë, pak gabime linti, duplikim minimal |

**Dëshmia:** output i `ruff check --isolated`, `jscpd`, `scc`; file:rresht.

## 4. Testet (`tests`), 10 pikë

| Niveli | Pikë | Përshkrimi |
|---|---|---|
| missing | 0 | Nuk ka asnjë test |
| partial | 4-7 | Ka teste, por mbulojnë pjesë të vogla ose nuk ekzekutohen |
| complete | 8-10 | Teste për funksionalitetin kryesor që ekzekutohen me sukses |

**Dëshmia:** emrat e file-ave të testeve (file:rresht), output i ekzekutimit në sandbox.

## 5. Dokumentimi (`documentation`), 10 pikë

| Niveli | Pikë | Përshkrimi |
|---|---|---|
| missing | 0 | Pa README ose README bosh |
| partial | 4-7 | README me përshkrim, por pa udhëzime instalimi/përdorimi |
| complete | 8-10 | Përshkrim, instalim, përdorim; komente ku logjika është e vështirë |

**Dëshmia:** file:rresht te README dhe në kod.

## 6. Procesi në git (`git_process`), 10 pikë

| Niveli | Pikë | Përshkrimi |
|---|---|---|
| missing | 0 | Një commit i vetëm me gjithë projektin |
| partial | 4-7 | Pak commit-e, mesazhe të paqarta ose punë e grumbulluar në pak ditë |
| complete | 8-10 | Commit-e të rregullta gjatë kohës, me mesazhe kuptimplota |

**Dëshmia:** output i `git -C work/<repo> log ...`, hash-et e commit-eve.
"Ndryshim drastik" (shumica e kodit në 1-2 commit pas javësh pa aktivitet)
regjistrohet si finding `drastic_history`, jo si provë kopjimi.

## 7. Siguria (`security`), 10 pikë

| Niveli | Pikë | Përshkrimi |
|---|---|---|
| missing | 0 | Secrets të rrjedhur ose probleme serioze sigurie |
| partial | 4-7 | Pa secrets, por me praktika të rrezikshme (p.sh. `eval` mbi input) |
| complete | 8-10 | Pa secrets në kod dhe në histori; inputi trajtohet me kujdes |

**Dëshmia:** output i `gitleaks detect --redact` (gjithmonë me config-un e projektit).
Rregull special: secret i konfirmuar → `security = 0` (e zbaton `score.py`).

## 8. Origjinaliteti (`originality`), 10 pikë

| Niveli | Pikë | Përshkrimi |
|---|---|---|
| missing | 0 | Pjesa më e madhe e kodit është e kopjuar pa atribuim |
| partial | 4-7 | Pjesë të kopjuara pa atribuim |
| complete | 8-10 | Pa përputhje të forta, ose me atribuim të qartë |

**Dëshmia:** URL e përputhjes nga `gh search code`, ose output i kërkimit pa rezultate,
plus raporti i `scripts/history_originality.py` për çdo repo kandidate.

**Kopjim i fshehur në histori.** Kontrolli nuk kufizohet te HEAD: studenti mund ta
kopjojë një projekt identik në një commit të hershëm dhe pastaj ta ndryshojë
(emra, formatim, renditje) që të mos duket. Script-i krahason çdo commit me
historinë e repo-s kandidate:

- **file identike**: i njëjti git blob hash = i njëjti file bajt për bajt
- **ngjashmëria e tekstit**: si duket kodi
- **ngjashmëria e strukturës**: kodi pa emra, komente e formatim

Kur teksti bie por struktura mbetet, ndryshimet kanë qenë kozmetike → finding
`copied_then_disguised`. Kërkim që dështoi (rate limit, pa kyçje) **nuk** është
dëshmi origjinaliteti.

Rregull special: përputhja (`originality_match` ose `copied_then_disguised`) ngre
flamur për njeriun, **nuk ka zbritje automatike**, sepse mund të jetë kod fillestar
i kursit, tutorial ose librari e lejuar.

---

## Flamujt për rishikim njerëzor

`score.py` del me kod 3 dhe `final.md` fillon me "Kërkon rishikim njerëzor" kur:
secret i konfirmuar, përputhje origjinaliteti, tentim manipulimi (injection),
histori drastike, më shumë se 3 kritere të paverifikueshme, ose kur Professor-i
e ndryshon totalin me më shumë se 15 pikë.

## Shkalla 5-10

91-100 → 10 · 81-90 → 9 · 71-80 → 8 · 61-70 → 7 · 51-60 → 6 · 0-50 → 5
