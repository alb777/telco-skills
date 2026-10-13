# telco-skills

Agent skills for mobile core signalling troubleshooting. Offline, no dependencies beyond `python3`, and every answer names the RFC or 3GPP/ITU-T spec it comes from.

![telcode looking up a Diameter code, searching across tables, decoding TBCD, and Claude Code answering an S6a question with the skill](docs/demo.gif)

| Skill | What it does |
|---|---|
| [`telcode`](skills/telcode/SKILL.md) | Diameter, 5G/4G NAS, 5G SBA, GTPv2-C, PFCP, GSM MAP, SCCP, Q.850 and SIP code lookup, S6a to NAS reject mapping, IMSI split, TBCD decoding |

## Why

Telecom codes collide. `5001` is `DIAMETER_AVP_UNSUPPORTED` in a Result-Code and `DIAMETER_ERROR_USER_UNKNOWN` in a 3GPP Experimental-Result. `27` is `absentSubscriber` in MAP and "Destination out of order" in Q.850. Answering from memory means guessing which table applies, and an unassigned code looks the same as one you don't remember. `telcode` answers from tables generated from the registries and specs, shows every table a number belongs to, and the skill tells the agent which fact decides between them.

## Install

Any agent that supports [Agent Skills](https://agentskills.io) (Claude Code, Codex, Cursor, Gemini CLI, GitHub Copilot, OpenCode and others):

```bash
npx skills add alb777/telco-skills
```

Claude Code plugin:

```
/plugin marketplace add alb777/telco-skills
/plugin install telco-skills@telco-skills
```

Plain CLI, no agent:

```bash
git clone https://github.com/alb777/telco-skills
ln -s "$PWD/telco-skills/skills/telcode/scripts/telcode.py" ~/.local/bin/telcode
```

## Usage

```console
$ telcode 5001
5001
  Diameter Result-Code (AVP 268)
    DIAMETER_AVP_UNSUPPORTED
    class: Permanent Failure | ref: RFC 6733
    note: Base protocol meaning: an AVP with the M-bit set is not supported by the receiver. The
          offending AVP is in Failed-AVP. Not the same as 3GPP Experimental-Result-Code 5001
          (DIAMETER_ERROR_USER_UNKNOWN).
  Diameter Experimental-Result-Code (AVP 298), 3GPP, Vendor-Id 10415
    DIAMETER_ERROR_USER_UNKNOWN
    class: Permanent Failure | ref: 3GPP TS 29.229
    note: Defined for Cx (TS 29.229) and reused by S6a/S6d (TS 29.272), Sh and others: the HSS does
          not know the user. On S6a ULR or AIR it usually means the IMSI is not provisioned, and the
          UE sees EMM #8 (TS 29.272 Annex A). Not the same as base Result-Code 5001
          (DIAMETER_AVP_UNSUPPORTED).
More than one table uses 5001: the protocol or AVP it came from decides which one applies. Use
--table to narrow it down.

$ telcode 5430 --table diameter-exp
5430
  Diameter Experimental-Result-Code (AVP 298), 3GPP, Vendor-Id 10415
    (not assigned)
    class: Permanent Failure | Reserved for 3GPP TS 29.272

$ telcode 15 --table emm
15
  EMM cause (4G NAS mobility management: attach, TAU and service, incl. LTE-M and NB-IoT)
    No Suitable Cells In tracking area
    ref: 3GPP TS 24.301
    note: The UE adds the tracking area to its forbidden list for roaming and looks for another
          tracking area in the same PLMN. Usual S6a causes behind it: 5420 without Error-Diagnostic,
          5421, 5004 with ODB_ALL_APN, 3002 or 3003, or the HSS being unreachable (TS 29.272 Annex
          A).

$ telcode NF_CONGESTION
NF_CONGESTION
  5G SBA ProblemDetails cause (AMF, SMF, UDM, UDR, AUSF, PCF, NRF, NSSF, SCP, SEPP)
    HTTP 503 | ref: 3GPP TS 29.500, SCP or SEPP
      The SCP or SEPP experiences congestion and performs overload control, which does not allow the
      request to be processed
    HTTP 503 | ref: 3GPP TS 29.500, any NF
      The NF instance experiences congestion and performs overload control, which does not allow the
      request to be processed
More than one entry defines NF_CONGESTION: the NF or service API that answered decides which one
applies.

$ telcode search absent
Diameter Experimental-Result-Code (AVP 298), 3GPP, Vendor-Id 10415
   4201  DIAMETER_ERROR_ABSENT_USER  (3GPP TS 29.173)
   5106  DIAMETER_ERROR_SUBS_DATA_ABSENT  (3GPP TS 29.329)
   5550  DIAMETER_ERROR_ABSENT_USER  (3GPP TS 29.338)
5G SBA ProblemDetails cause (AMF, SMF, UDM, UDR, AUSF, PCF, NRF, NSSF, SCP, SEPP)
    404  ABSENT_SUBSCRIBER_SM  (3GPP TS 29.503, Nudm_UEContextManagement)
GSM MAP error code (TCAP ReturnError, local value)
      6  absentSubscriberSM  (3GPP TS 29.002, MAP-Errors)
     27  absentSubscriber  (3GPP TS 29.002, MAP-Errors)
Q.850 cause value (ISUP, DSS1, SIP Reason header)
     20  Subscriber absent  (ITU-T Q.850)

$ telcode imsi 262011234567890
IMSI 262011234567890
  MNC length 2:  MCC 262  MNC 01   MSIN 1234567890
  MNC length 3:  MCC 262  MNC 011  MSIN 234567890
The IMSI does not encode the MNC length. The SIM states it in EF_AD (3GPP TS 31.102); pass --mnc-len
2 or 3 when you know it.

$ telcode tbcd 62 02 11 32 54 76 98 f0
262011234567890
```

5G SBA causes are looked up by name, in any case (`telcode user_not_found`). `telcode search 29.272` lists every code a TS defines, `telcode tables` shows the sources, and `--json` gives machine-readable output on every command. Exit codes: 0 found, 1 nothing found, 2 bad input.

## Data

| Table | Codes | Source |
|---|---|---|
| Diameter Result-Code | 72 | IANA AAA Parameters registry |
| Diameter Experimental-Result-Code, 3GPP | 149 | 3GPP TS 29.230 V19.3.0, tables 8.1.2 to 8.1.4 |
| 5GMM cause | 50 | 3GPP TS 24.501 V20.1.0, table 9.11.3.2.1 |
| 5GSM cause | 46 | 3GPP TS 24.501 V20.1.0, table 9.11.4.2.1 |
| EMM cause | 41 | 3GPP TS 24.301 V20.1.0, table 9.9.3.9.1 |
| ESM cause | 47 | 3GPP TS 24.301 V20.1.0, table 9.9.4.4.1 |
| GTPv2-C cause | 82 | 3GPP TS 29.274 V20.0.0, table 8.4-1 |
| PFCP cause | 32 | 3GPP TS 29.244 V20.1.0, table 8.2.1-1 |
| 5G SBA ProblemDetails cause | 215 | 3GPP TS 29.500 V20.0.0 and the application error tables of TS 29.502, 29.503, 29.504, 29.507, 29.509, 29.510, 29.512, 29.514, 29.518 and 29.531 (Release 20) |
| GSM MAP errors | 56 | 3GPP TS 29.002 V19.1.0, ASN.1 module MAP-Errors |
| SCCP return cause | 15 | ITU-T Q.713 (03/2001), clause 3.12 |
| Q.850 cause | 72 | ITU-T Q.850 (10/2018) with Amendment 1 (04/2019) |
| SIP response | 75 | IANA SIP Parameters registry |

`tools/update_data.py` regenerates the IANA and 3GPP tables straight from the registries and the 3GPP spec archive. The two ITU-T tables are small, stable and only published as PDF, so they are maintained by hand. Names are kept as the sources spell them, typos included. The tables were cross-checked against Wireshark's dissectors when they were built. The notes on S6a errors and EMM causes follow the mapping in TS 29.272 Annex A, so a device side reject can be traced back to the HSS answer behind it. A 5G SBA cause name is only unique within one service API, so each SBA entry keeps the HTTP status and wording of the APIs that define it.

Not covered yet: SBA causes of NFs outside the specs above (NEF, CHF, SMSF and others), the OAuth 2.0 errors of Nnrf_AccessToken, NGAP and S1AP causes, GTPv1 causes, AVP codes, command codes and application ids, MAP operation codes, TCAP Reject problem codes, vendor specific Experimental-Result codes, and MCC/MNC to country or operator names.

## Development

```bash
python3 -m unittest discover -s tests
uvx ruff check . && uvx ruff format --check .
uvx mypy
python3 tools/update_data.py    # refresh the IANA and 3GPP tables
python3 tools/record_demo.py    # re-record docs/demo.gif, needs agg and claude on PATH
```

## License

MIT. Code values and names are facts taken from IANA, 3GPP and ITU-T publications; the specifications themselves belong to their publishers.
