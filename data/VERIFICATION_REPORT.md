# RIT Institutional Assistant - Curated Facts Verification Report

This report is generated automatically by `tools/verify_curated.py`.
It checks all curated manual facts (`fees.csv`, `cutoffs.csv`, `hods.csv`) against verified scraped data.

## 1. Fees Verification (`data/manual/fees.csv`)

| Item | Curated value | Status | Evidence | Action for me |
|---|---|---|---|---|
| B.Tech | Tuition: 136522 | **MATCHED** | exam_details::pdf::Mandatory_Disclosure (https://ritindia.edu/ritwebsite/admin/upload/file/Mandatory-Disclosure-2026-27.pdf); fee_structure (https://ritindia.edu/ritwebsite/website/aboutus.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjNjNTE3YTFkYjI3Nw_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwNmVjNTRjNg) | Keep verified figure |
| B.Tech (Open Category) | Rs. 1,36,522 per year (100% Tuition Fee) | **MATCHED** | exam_details::pdf::Mandatory_Disclosure (https://ritindia.edu/ritwebsite/admin/upload/file/Mandatory-Disclosure-2026-27.pdf); fee_structure (https://ritindia.edu/ritwebsite/website/aboutus.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjNjNTE3YTFkYjI3Nw_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwNmVjNTRjNg) | Keep verified figure |
| B.Tech (OBC EBC) | Rs. 68,261 per year (50% Tuition Fee concession via Rajarshi... | **MATCHED** | fee_structure (https://ritindia.edu/ritwebsite/website/aboutus.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjNjNTE3YTFkYjI3Nw_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwNmVjNTRjNg) [Informational: OBC/EBC amount (68,261) is exactly half of Open (1,36,522)] | Keep verified figure |
| B.Tech (SC ST) | Rs. 0 Tuition Fee (100% fee exemption under Government of Ma... | **NOT FOUND** | None found in legacy/scraped pages | UNVERIFIED — needs the official fee notice |
| B.Tech (VJNT SBC TFWS) | Rs. 0 Tuition Fee (100% Tuition Fee waiver under Tuition Fee... | **NOT FOUND** | None found in legacy/scraped pages | UNVERIFIED — needs the official fee notice |
| B.Tech (Institutional Management Quota) | Full approved fee of Rs. 1,36,522 per year without governmen... | **MATCHED** | exam_details::pdf::Mandatory_Disclosure (https://ritindia.edu/ritwebsite/admin/upload/file/Mandatory-Disclosure-2026-27.pdf); fee_structure (https://ritindia.edu/ritwebsite/website/aboutus.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjNjNTE3YTFkYjI3Nw_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwNmVjNTRjNg) | Keep verified figure |
| MBA | Tuition: 83478 | **MATCHED** | exam_details::pdf::Mandatory_Disclosure (https://ritindia.edu/ritwebsite/admin/upload/file/Mandatory-Disclosure-2026-27.pdf); fee_structure (https://ritindia.edu/ritwebsite/website/aboutus.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjNjNTE3YTFkYjI3Nw_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwNmVjNTRjNg) | Keep verified figure |
| MCA | Tuition: 40909 | **MATCHED** | exam_details::pdf::Mandatory_Disclosure (https://ritindia.edu/ritwebsite/admin/upload/file/Mandatory-Disclosure-2026-27.pdf) | Keep verified figure |
| BBA | Tuition: 36000 | **MATCHED** | exam_details::pdf::Mandatory_Disclosure (https://ritindia.edu/ritwebsite/admin/upload/file/Mandatory-Disclosure-2026-27.pdf) | Keep verified figure |
| DIPLOMA | Tuition: 41178 | **MATCHED** | exam_details::pdf::Mandatory_Disclosure (https://ritindia.edu/ritwebsite/admin/upload/file/Mandatory-Disclosure-2026-27.pdf); fee_structure (https://ritindia.edu/ritwebsite/website/aboutus.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjNjNTE3YTFkYjI3Nw_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwNmVjNTRjNg) | Keep verified figure |

## 2. Cut-offs Verification (`data/manual/cutoffs.csv`)

| Item | Curated value | Status | Evidence | Action for me |
|---|---|---|---|---|
| Computer Engineering | Rank 20264, 93.25% | **MATCHED** | FY-BTech-CutOff-2024-25.pdf, p.1, COMP. ENGG (FY B.Tech 2024-25 CAP I Gents/Open) | Duplicate of PDF cutoff_cells; propose updated context or drop |
| Computer Science and Engineering (Artificial Intelligence and Machine Learning) | Rank 23212, 92.28% | **MATCHED** | FY-BTech-CutOff-2024-25.pdf, p.1, CSE (AIML) (FY B.Tech 2024-25 CAP I Gents/Open) | Duplicate of PDF cutoff_cells; propose updated context or drop |
| Computer Science and Information Technology | Rank 23018, 92.32% | **MATCHED** | FY-BTech-CutOff-2024-25.pdf, p.1, CS & IT (FY B.Tech 2024-25 CAP I Gents/Open) | Duplicate of PDF cutoff_cells; propose updated context or drop |
| Electronics and Telecommunication Engineering | Rank 30908, 89.54% | **MATCHED** | FY-BTech-CutOff-2024-25.pdf, p.1, ETC (FY B.Tech 2024-25 CAP I Gents/Open) | Duplicate of PDF cutoff_cells; propose updated context or drop |
| Electrical Engineering | Rank 45176, 84.51% | **MATCHED** | FY-BTech-CutOff-2024-25.pdf, p.1, ELECT (FY B.Tech 2024-25 CAP I Gents/Open) | Duplicate of PDF cutoff_cells; propose updated context or drop |
| Civil Engineering | Rank 51668, 82.15% | **MATCHED** | FY-BTech-CutOff-2024-25.pdf, p.1, CIVIL (FY B.Tech 2024-25 CAP I Gents/Open) | Duplicate of PDF cutoff_cells; propose updated context or drop |
| Robotics and Automation | Rank 56827, 80.27% | **MATCHED** | FY-BTech-CutOff-2024-25.pdf, p.1, Robotics (FY B.Tech 2024-25 CAP I Gents/Open) | Duplicate of PDF cutoff_cells; propose updated context or drop |
| Mechatronics Engineering | Rank 58738, 79.52% | **MATCHED** | FY-BTech-CutOff-2024-25.pdf, p.1, MECH ATRON ICS (FY B.Tech 2024-25 CAP I Gents/Open) | Duplicate of PDF cutoff_cells; propose updated context or drop |
| Mechanical Engineering | Rank 63490, 77.82% | **MATCHED** | FY-BTech-CutOff-2024-25.pdf, p.1, MECH (FY B.Tech 2024-25 CAP I Gents/Open) | Duplicate of PDF cutoff_cells; propose updated context or drop |
| MBA | Rank 31116, 43.57% | **NOT FOUND** | No matching branch/cell in cutoff_cells | Keep curated figure with unverified warning (no source PDF) |
| MCA | Rank 8625, 64.63% | **NOT FOUND** | No matching branch/cell in cutoff_cells | Keep curated figure with unverified warning (no source PDF) |
| BBA | Rank 32099, 32.48% | **NOT FOUND** | No matching branch/cell in cutoff_cells | Keep curated figure with unverified warning (no source PDF) |
| BCA | Rank 37585, 19.46% | **NOT FOUND** | No matching branch/cell in cutoff_cells | Keep curated figure with unverified warning (no source PDF) |

## 3. HODs Verification (`data/manual/hods.csv`)

| Item | Curated value | Status | Evidence | Action for me |
|---|---|---|---|---|
| Sciences & Humanities | Dr. M. B. Mandale | **MATCHED** | Exact name in HOD message (https://ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjM0Njc1MDc1YzJkNg_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw) | Keep verified HOD |
| Robotics and Automation | Dr. S. R. Desai | **PARTIAL** | Abbreviated in CSV vs HOD message signature 'Dr. Sandeep R. Desai Head of the Department Robotics and Automation Department' (https://ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjQ5MmNmMzg1NDk1Yg_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw) | Confirm full name expansion |
| Civil Engineering | Dr. P. D. Kumbhar | **MATCHED** | Exact name in HOD message (https://ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjMyYTk4ZDQxMDQyMA_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw) | Keep verified HOD |
| Computer Science & Engineering | Dr. Sachin S. Patil | **MATCHED** | Exact name in HOD message (https://ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjMyYTk4ZTVmMjk5Yw_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw) | Keep verified HOD |
| Computer Science & Engineering (Artificial Intelligence & Machine Learning) | Dr. R. A. Medar | **MATCHED** | Exact name in HOD message (https://ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjM0MTM2MGEyZWQwZg_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw) | Keep verified HOD |
| Electrical Engineering | Dr. V. N. Kalkhambkar | **NOT FOUND** | Absent from department page text (https://ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjM0MTM2MmIyM2YxZQ_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw) | Needs official appointment letter or website confirmation |
| Electronics and Telecommunication Engineering | Dr. Mahadev S. Patil | **MATCHED** | Exact name in HOD message (https://ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjM0MTM2NWY3M2E0Ng_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw) | Keep verified HOD |
| Information Technology | Dr. A. C. Adamuthe | **MATCHED** | Exact name in HOD message (https://ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjM0MTM2N2I3NzY5Yg_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw) | Keep verified HOD |
| Mechanical Engineering | Dr. S. B. Kumbhar | **MATCHED** | Exact name in HOD message (https://ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjM0MTM2ODdlYTZiZQ_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw) | Keep verified HOD |
| Mechatronics Engineering | Dr. Shailesh Shirguppikar | **MATCHED** | Exact name in HOD message (https://ritindia.edu/ritwebsite/website/department.php?idsfvsisdcbqusa=aWRzZnZzaXNkY2JxdXNhNDZlM2Q3NzJhMTg4OGVhZGZmMjZjN2FkYTQ3ZmQ3NTAyZDc5NmUwN_MNjM0MTM2OTViMjk1ZA_nZzaXNkY2JxdXNhNDZlM2Q3Nz__12_NjMyMTgwN2I5ZTdlMw) | Keep verified HOD |

## 4. Decisions Needed From User

1. **Drop the 9 fully matched B.Tech rows of `cutoffs.csv` in favour of the PDF values?**
   - The 9 B.Tech rows in `cutoffs.csv` are identical duplicates of the values already indexed in `cutoff_cells` from `fy-btech-cutoff-2024-25.pdf` (FY B.Tech CAP I 2024-25 Gents Open SML NO).
   - `data/manual/cutoffs.proposed.csv` has been generated with precise context and source URLs.
   - Shall we replace `cutoffs.csv` with `cutoffs.proposed.csv` or drop the 9 duplicate B.Tech rows from the manual CSV?

2. **Is Dr. S. R. Desai really HOD of both Robotics & Automation and Automobile Engineering?**
   - On the Robotics page, the HOD message is signed `Dr. Sandeep R. Desai, Head of the Department Robotics and Automation`.
   - On the Automobile Engineering page, the HOD message is also signed `Dr. S. R. Desai`.
   - Please confirm if Dr. Desai serves as Head for both departments.

3. **Source of the Electrical Engineering HOD (`Dr. V. N. Kalkhambkar`)**
   - The HOD message on the Electrical Engineering department page is unsigned.
   - However, `Dr. V. N. Kalkhambkar` is confirmed in the official RIT PhD research guide list (`PhD-student-List-Electrical.pdf`).
   - Please confirm whether to accept this attribution from the PhD supervisor records.
