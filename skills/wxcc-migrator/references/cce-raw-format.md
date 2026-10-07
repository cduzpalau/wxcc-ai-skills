# CCE configuration export (.raw) – binary format

## What the files are

ICMDBA (**Data > Export**) writes one file per ICM configuration table. The extension is `.raw`, and each file is a **SQL Server `bcp` native-format** dump:

- There is no header, no delimiter and no row terminator. Rows are back to back, and each row is the table's columns in physical order.
- A file name is the table name abbreviated. Each word of the table name is cut to its first 2 letters (`Skill_Group_Member` → `SkGrMe`). A one-word table is cut to 8 letters (`Agent`, `Attribut`). Two-word tables are cut to 4 + 4 letters (`SkilGrou`, `DialNumb`, `CallType`).
- The `Version` file is plain text and holds the export schema version (`233 0 0 0` in the sample).
- A 0-byte file is a table with no rows.

## Field encodings (little-endian)

| Code | SQL type | Bytes on disk |
|---|---|---|
| `I4` | int NOT NULL | 4 |
| `I2` | smallint NOT NULL | 2 |
| `I1` | tinyint NOT NULL | 1 |
| `C1` | char(1) NOT NULL | 1 ASCII byte (`Y`/`N` flags) |
| `DT` | datetime NOT NULL | 8: int32 days since 1900-01-01, then uint32 ticks of 1/300 s |
| `F8` | float NOT NULL | 8 |
| `VC` | varchar / nullable char | 2-byte length, then the bytes. `FF FF` = NULL. `00 00` = empty string |
| `FN` | any **nullable** fixed type | 1-byte length (`01`/`02`/`04`/`08`), then the value. `FF` = NULL. Length 8 is a datetime |
| `TXT` | text / image | 4-byte length, then the bytes (`Script_Data`) |

`FN` describes itself, so you never need to know whether a nullable column is an int, a smallint or a datetime.

The ambiguous types are the NOT NULL fixed ones: `I4`, `I2`, `C1` and `DT` all accept any bytes. Most layout work goes into telling them apart.

## Tells that make layouts quick to find

- Row 1 almost always starts with an `I4` primary key in the 5000 range (`88 13 00 00` = 5000). The next row starts with the next ID, so the first row's length is clear from the hex.
- `88 13` on its own is a **smallint** PeripheralID or RoutingClientID (`I2`).
- `04 xx xx 00 00` is a nullable int (`FN`). `FF` on its own is a NULL `FN`. `FF FF` is a NULL `VC`.
- `08` followed by 8 bytes, with a day count around `a6..b2 00 00` (years 2016–2025), is the `DateTimeStamp` near the end of the row.
- `N` / `Y` bytes between fields are `Deleted` and other flags (`C1`).
- `ChangeStamp` is an `I4` holding a small number, just before `DepartmentID` (`FN`, usually `FF`) and `DateTimeStamp`.
- If the guess is `VC` but the next byte is `00` and the column is never a string, it is an `I2`. `00 00` and `01 00` followed by `N` were `I2`, not empty strings (`Person`).

## Adding a table live (the hybrid step)

1. Read `1-decoded/_unknown_preview/<File>.txt`. It holds the printable strings and the first 256 bytes in hex.
2. Draft a layout and step through row 1:
   `python3 scripts/cce_decode.py walk "<export>/<File>.raw" "ID:I4 EnterpriseName:VC Desc:VC Deleted:C1 ChangeStamp:I4 DepartmentID:FN DateTimeStamp:FN"`
   `next @N` shows what follows. It should be the next row's ID.
3. Prove the layout over the whole file:
   `python3 scripts/cce_decode.py profile "<export>/<File>.raw" "<layout>"`
   The layout is right when it reports `OK: <n> rows, all <bytes> bytes consumed`. Check that the distinct values make sense: IDs unique, flags only Y/N, dates plausible.
4. Add it to `references/cce_schemas.json` as `"<File>": {"table": "<Table_Name>", "columns": [["Col","TYPE"], ...]}`, then re-run `decode`.
5. Name a column only when the data proves its meaning. Otherwise keep `c<N>`. If you guessed a name, say so in the report.

## Coverage of the shipped layouts

There are 27 tables. Each one was checked byte for byte against the sample export (CCE 12.x, dCloud "Cumulus"):

Agent, Person, Attribute, Agent_Attribute, Agent_Team, Agent_Team_Member, Agent_Team_Supervisor, Skill_Group, Skill_Group_Member, Precision_Queue, Precision_Queue_Step, Precision_Queue_Term, Media_Routing_Domain, Call_Type, Call_Type_Map, Dialed_Number, Dialed_Number_Map, Routing_Client, Peripheral, Reason_Code, Expanded_Call_Variable, Agent_Desk_Settings, Master_Script, Script, Label, Route, Campaign_Skill_Group.

Column meanings that were **inferred from the data** (check them on a new customer export):

- `Attribute.AttributeDataType`: 3 = Boolean, 4 = Proficiency. The values 1 = Text and 2 = Integer are assumed.
- `Precision_Queue_Term.AttributeRelation`: 1 `==`, 2 `!=`, 3 `<`, 4 `<=`, 5 `>`, 6 `>=`. `TermRelation`: 0 = first term, 1 = AND, 2 = OR.
- `Reason_Code.ReasonCodeUsage` is a bitmask: 1 = Not Ready, 2 = Wrap-up, 4 = Logout/system.
- `Skill_Group.DefaultEntry` = 1 marks the auto-created per-MRD default skill group.
- `Expanded_Call_Variable` flags are `ECCArray`, `Enabled`, `CiscoProvided` and `Persistent`.
- `Precision_Queue`: the last column is `MRDomainID`.
- `Person.Email` holds a UPN/e-mail on newer releases and is often empty.
- `Agent_Desk_Settings`: only the name is mapped. The other fields are decoded but have no names yet.

`Script_Data` (ScriData.raw, 4 MB) holds the compiled ICM routing scripts. It is not decoded, so routing logic is rebuilt as WxCC flows from `flow_inventory.csv` and `routing_requirements.json`.

Passwords (`Person.Password`, stored `{enc:1}...`) are always masked in decoded output.
