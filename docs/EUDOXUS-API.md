# Eudoxus REST API — verified reference

Probed live against `https://service.eudoxus.gr` on 2026-07-22.
No API key required. Undocumented and unversioned — treat as liable to change without notice.

Base: `https://service.eudoxus.gr/coursebooks/rest/`

The endpoint list below was extracted from the SPA bundle
(`/coursebooks/courseBooksUIFactory/dist/js/app.*.js`) and each entry was then exercised
directly.

---

## Endpoints

### `GET courses-books/academic-years`

```json
{"activeYear": 2025, "editedYear": 2026,
 "yearsList": [{"year": 2026, "yearLabel": "2026 - 2027(Υπό Διαμόρφωση Έτος)"}, ...]}
```

Years 2010–2026. `year=2025` means academic year 2025–2026.

### `GET courses-books/secretariat-academics`

Returns the entire institution/department tree in one call.

```
{
  "institutions":         [{"id", "name"}]          // 747 rows, duplicated per department
  "institutionAcademics": { "<institutionId>": [ {...academic} ] }
  "academicSecretariats": { "<academicId>":     {...secretariat} }
}
```

`academic` record:

```json
{"id": 119, "secretariatId": null, "institution": "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ",
 "school": "ΝΟΜΙΚΗ", "department": "ΝΟΜΙΚΗΣ", "institutionID": 8,
 "webServiceStatus": true, "blockCloneCourses": false, "useIdGram": false}
```

`secretariat` record carries departmental contact details: address, city, prefecture, and
(often null) phone/email fields.

Counts: 48 institutions, 747 department records, 503 of which are live — the remainder are
marked `(ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)` or `(Συγχωνεύτηκε)` in the department name.

### `GET courses-books/get-semesters-courses?secretariatId={sid}&year={y}`

Returns `{ "<semester>": [ course, ... ] }`.

```json
{"id": 143780402, "title": "ΕΜΠΡΑΓΜΑΤΟ ΔΙΚΑΙΟ",
 "professor": "Γ. Καρυμπαλη-Τσιπτσιου, Ά. Κορνηλάκης, Α. Φουντεδακη",
 "code": "Υ16", "year": 2025, "semester": 0, "period": "Ximerino",
 "secretariatID": 2845, "booksSource": "EUDOXUS", "comment": ""}
```

> ### ⚠ The `secretariatId` trap
>
> `secretariatId` is **not** `institutionAcademics[].id`, and **not**
> `institutionAcademics[].secretariatId` (that field is always `null`).
>
> It is `academicSecretariats[<academicId>].id` — the inner id.
>
> Example: ΑΠΘ Νομικής has `academicId = 119` → `secretariatId = 2845`.
>
> **A wrong id returns `{}` with HTTP 200.** No error, no warning. This is the single most
> dangerous behaviour of this API: an entire faculty silently missing looks exactly like a
> faculty with no courses. Always cross-check an empty result against a prior year before
> accepting it.

### `GET courses-books/course/{courseId}/books`

Returns the course again, plus `bookgroups[].books[].book` with the full book record:

```json
{"id": 102072561, "type": "Published", "active": true,
 "title": "Εμπράγματο δίκαιο Επίτομο", "subtitle": null,
 "authors": "Παπαστερίου Δημήτριος Η.", "isbn": "9789604456888",
 "editionNumber": "1η", "publicationYear": 2011,
 "editorialHouse": "Σάκκκουλας Εκδόσεις Α.Ε.",
 "publisherId": "261", "publisherName": "ΕΚΔΟΣΕΙΣ ΣΑΚΚΟΥΛΑ ΑΕ",
 "description": null, "binding": "Soft", "keywords": [], "subjects": [],
 "dimensions": "17x24", "pages": 864,
 "pathToCover": "61/cover-102072561.jpg", "pathToTOC": "61/toc-102072561.pdf",
 "pathToChapter": "61/chapter-102072561.pdf",
 "linkToPublisher": "http://www.sakkoulas.gr/..."}
```

`keywords` and `subjects` are present in the schema but were empty in every record sampled.
Do not rely on them for subject classification.

### `GET courses-books/book/eudoxus/info?isbn={isbn}` · `?bookId={id}`

Returns a **JSON array** (not an object) of matching book records.

### `GET courses-books/book/eudoxus/courses?isbn={isbn}&year={y}` · `?bookId=`

Reverse index — which courses distribute a given book.

```
{ "<bookId>": { "<institutionName>": [ {"departmentName", "course": {...}} ] } }
```

Empty result is `{"<bookId>": {}}`. Drives competitive-share and decay analysis.

### `GET courses-books/book/eudoxus/extract-csv?secretariatId={sid}&year={y}`

Bulk CSV for a whole department-year. Preferred ingestion path where available — far fewer
requests than walking courses individually. Keep as fallback if the JSON endpoints change.

### `GET courses-books/book/eudoxus/courses/export-csv?bookId={id}&year={y}`

CSV of the reverse index.

### `POST courses-books/verify-recaptcha`

Session gate. The SPA stores `recaptcha_verified` in `localStorage` after a successful
verification. Harvesting must hold one verified session and reuse it. On challenge: **stop
and alert a human.** Do not attempt to solve or evade.

---

## Publisher identity

`publisherId = "149848"` = `ΕΚΔΟΣΕΙΣ ΚΥΡΙΑΚΙΔΗ ΜΟΝΟΠΡΟΣΩΠΗ ΙΚΕ`.

Note `editorialHouse` is free text and inconsistently cased
(`ΕΚΔΟΣΕΙΣ ΚΥΡΙΑΚΙΔΗ ΜΟΝΟΠΡΟΣΩΠΗ ΙΚΕ` vs `Εκδόσεις Κυριακίδη Μονοπρόσωπη ΙΚΕ`).
Always key on `publisherId`, never on the name.

---

## Observed data quality in the `professor` field

Real values, verbatim. These constitute the normaliser's regression corpus.

| Value | Problem |
|---|---|
| `Αθανάσιος Γκίκας` | Given-then-surname (author field uses surname-then-given) |
| `ΜΠΕΤΣΑΣ ΙΩΑΝΝΗΣ` | All caps, surname-then-given, accents dropped by uppercasing |
| `ΖΕΡΒΟΥΔΑΚΗΣ Γ.` | Surname then trailing initial |
| `Γ. Καρυμπαλη-Τσιπτσιου` | Leading initial, accents omitted, hyphenated surname |
| `Α.Βαλτούδης` | No space after the initial's period |
| `ΑΝΑΣΤΑΣΙΟΥ` | Surname only |
| `ΦΩΤΙΟΣ ΑΠΟΣΤΟΛΟΣ` | Ambiguous — both tokens are plausible surnames |
| `ΑΝΑΘΕΣΗ` | **Not a person.** Placeholder meaning the assignment is pending |
| `""` | Empty (observed: Γεωπονίας Πατρών, ΔΙΠΑΕ Γεωπονίας) |
| `Μητρ. Κίτρους, Χρυσοστόμου Γεώργιος και Χειλάς Γεώργιος` | Ecclesiastical rank as prefix; ` και ` used as a separator alongside `,` |
| 16 names in one comma-separated field | Team-taught course; "the distributing professor" is not well defined |

---

## Rate limiting and etiquette

- Full national harvest is ~500 department-years per academic year. Trivial volume; there is
  no reason to be aggressive.
- Default to ≤2 requests/second, ≤4 concurrent, and honour `Retry-After`.
- Harvest annually, not continuously. Content-addressed snapshots make re-runs free.
- Send a descriptive `User-Agent` with a contact address.
- Check `robots.txt` and the site terms before any bulk run.
