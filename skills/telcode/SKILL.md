---
name: telcode
description: Offline lookup of mobile core signalling codes with spec references. Covers Diameter Result-Code and 3GPP Experimental-Result-Code (S6a/S6d, Cx, Sh, Gx, Rx, SWx, S13 and more), 5G and 4G NAS causes (5GMM, 5GSM, EMM, ESM), GTPv2-C and PFCP causes, GSM MAP error codes, SCCP return causes, ITU-T Q.850 cause values and SIP response codes, plus the official S6a to NAS reject mapping. Also splits IMSIs into MCC/MNC/MSIN and decodes TBCD octets from traces. Use when the user pastes a Diameter, NAS (attach, registration, PDN or PDU session reject), GTP, PFCP, SS7/SIGTRAN (MAP, TCAP, SCCP), ISUP or SIP error code, cause value, log line or pcap excerpt and asks what it means, including IoT devices (LTE-M, NB-IoT) that fail to attach, or needs an IMSI or TBCD-encoded number decoded.
license: MIT
metadata:
  version: "0.2.0"
---

# telcode

`scripts/telcode.py` answers from tables generated from IANA, 3GPP and ITU-T sources. It needs only `python3` (3.10+) and works offline. Prefer it over memory: telecom codes collide across tables, and a wrong guess sends people debugging the wrong layer.

## Commands

Call the script by its path inside this skill's directory, without `cd`, so a `python3` permission rule covers it. Add `--json` whenever you will read the output:

```bash
python3 scripts/telcode.py 5001 --json                 # every table that defines 5001
python3 scripts/telcode.py 27 --table map --json        # one table, by prefix (see below)
python3 scripts/telcode.py search absent subscriber --json
python3 scripts/telcode.py search 29.272 --json         # all codes specified in a TS
python3 scripts/telcode.py imsi 262011234567890 --json  # add --mnc-len 2|3 when known
python3 scripts/telcode.py tbcd 62 02 11 32 54 76 98 f0 --json
python3 scripts/telcode.py tables --json                # tables, versions, sources
```

Exit codes: 0 found, 1 nothing found, 2 bad input.

## Pick the right table before answering

The same number means different things in different tables. Work out where the number came from and pass `--table`:

| The number came from | Table |
|---|---|
| Diameter `Result-Code` AVP (268) | `diameter-result` |
| Diameter `Experimental-Result` AVP (297) with `Vendor-Id` 10415 and `Experimental-Result-Code` (298) | `diameter-experimental-3gpp` |
| 5G NAS Registration, Service or Deregistration reject (5GMM cause IE) | `5gmm-cause` |
| 5G NAS PDU session reject (5GSM cause IE) | `5gsm-cause` |
| 4G NAS Attach, TAU or Service reject, Detach (EMM cause IE) | `emm-cause` |
| 4G NAS PDN connectivity or bearer reject (ESM cause IE) | `esm-cause` |
| GTPv2-C Cause IE on S11, S4, S5/S8 or S10 | `gtpv2c-cause` |
| PFCP Cause IE on N4 or Sxa/Sxb/Sxc | `pfcp-cause` |
| TCAP ReturnError `errorCode` localValue in a MAP dialogue | `map-error` |
| SCCP UDTS, XUDTS or LUDTS return cause | `sccp-return-cause` |
| ISUP REL cause, DSS1 cause, SIP `Reason: Q.850;cause=N` | `q850-cause` |
| SIP status line | `sip-response` |

If the context does not say, run without `--table`, show every match and say which fact would decide. In 3GPP Diameter applications, failures specific to the application arrive as Experimental-Result. Base protocol failures (3xxx, and 5xxx such as 5001, 5004, 5005) arrive as Result-Code. An Experimental-Result with a `Vendor-Id` other than 10415 is outside these tables.

## Answering

1. Quote the name and the `ref` (RFC or TS) from the output, and the `note` when there is one.
2. When `name` is null the code is not assigned. Say so and report `class` and `ranges`, for example "reserved for 3GPP TS 29.272". Never invent a name.
3. For Diameter answers, ask for or look at `Failed-AVP`, `Error-Message` and `Error-Diagnostic`: they usually say which AVP or condition triggered the code.
4. A NAS reject seen by the device usually starts in the core. TS 29.272 Annex A maps S6a answers to EMM causes, and the notes carry that mapping both ways: EMM #15 often comes from S6a 5420, 5421 or 5004 with ODB_ALL_APN; EMM #8 from S6a 5001; EMM #19 wraps an ESM cause that says why the PDN connection failed; ESM #30 points at the GTPv2-C cause on S11 or S5/S8. Follow the chain one hop at a time and look up each hop.
5. Failures in the CER/CEA exchange (3010, 4003, 5010, 5017) are peer configuration problems: compare Origin-Host, Origin-Realm, application ids and security settings on both peers. The transport connection closes right after the CEA.
6. For an IMSI, never assume the MNC length: the IMSI does not encode it. Show both splits, or ask, unless the user gave it.
7. TBCD (TS 29.002) is how MAP, GTP and the Diameter MSISDN AVP carry IMSI, MSISDN and similar numbers: two digits per octet, low nibble first, `f` as filler. Decode with `tbcd` instead of by hand. SCCP global title digits use the same nibble order, but an odd/even indicator replaces the `f`: when it says odd, drop the trailing `0`.

## Not covered

5G SBA ProblemDetails causes (for example USER_NOT_FOUND), NGAP and S1AP causes, GTPv1 causes, AVP codes, Diameter command codes and application ids, MAP operation codes, TCAP Reject problem codes, vendor specific Experimental-Result codes, and MCC/MNC to country or operator names. Say that the tool does not cover them instead of answering from memory as if it did.
