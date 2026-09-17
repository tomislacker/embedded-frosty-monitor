# Compliance & certification roadmap

## Framing

Certification reduces and transfers risk. It does not make risk zero, and
no honest roadmap should imply otherwise. What FCC, UL/NRTL, and the rest
actually buy are three concrete things: (a) the legal right to market and
sell the product in the US, (b) NRTL listing that lets the electrical
inspectors, insurers, and commercial-kitchen operators who touch this
product accept it without a fight, and (c) a documented, defensible trail
of diligence that protects the business if something ever does go wrong.
That's the real goal behind "send this through FCC, UL, NEC, NFPA,
whomever" — not an unattainable zero-risk guarantee, but the standard set
of gates a legitimate electrical product installed in commercial food
equipment is expected to clear before it ships at volume.

## Product context matters

frosty-monitor spans two different regulatory postures, and conflating
them leads to either over-spending on the wrong tier or under-covering the
one that actually needs it:

- **DAQ Pro (Tier 3), as deployed today.** A portable diagnostic tool the
  business owns and operates, installed temporarily by the business's own
  qualified technician, then removed. This is closer to a piece of test
  equipment than a sold product — the obligations here are lighter (basic
  FCC Part 15 unintentional-radiator compliance for anything sold or
  offered for sale still applies, since DAQ Pro units are assembled from
  purchased parts and used commercially, but there's no NRTL-listing
  expectation from a host machine's AHJ when the business's own tech is
  the one plugging it in and unplugging it under the safety procedures in
  [docs/safety.md](safety.md)).
- **Guard, Logger, and Live (Tiers 1, 2, 4), as sold products.** These are
  permanently installed inside a customer's commercial equipment by
  whoever the customer has do the install, left running unattended for
  years, and are the kind of product an electrical inspector, an
  insurance underwriter, or a health inspector can reasonably ask "is this
  listed?" about. Full product compliance applies.

**Everything below targets the sold products** — Guard first, since it's
the simplest BOM and the first tier scheduled to ship (see
[docs/product-line.md](product-line.md#build-out-sequence)) — with notes
on where Logger and Live add scope.

## Per-regime sections

### FCC (Part 15)

**What it covers:** any electronic device sold in the US that can emit RF
energy, intentionally or not. Two separate things apply here:

- **Unintentional radiator (Part 15 Subpart B)** — the digital
  logic/switching circuitry on the board itself (the ESP32, the ADCs, the
  switching regulator) radiates RF as a side effect, whether or not it has
  a radio in it. This is the side *we* have to test and self-declare.
- **Intentional radiator (Part 15 Subpart C)** — the WiFi/BLE transmitter.
  Every tier that carries radio (Logger's BLE, Live's WiFi/cellular) uses
  a pre-certified module — this is the single biggest cost lever in this
  whole section. A module that already carries its own FCC grant (modular
  approval) means the transmitter side doesn't need full RF compliance
  testing from us; we inherit the module's certification as long as we
  follow its integration guide.

**Compliance path:**

1. Unintentional-radiator testing at an accredited EMC lab, per ANSI
   C63.4, covering radiated and conducted emissions from the board.
2. **Composite/host testing** is still required even with a pre-certified
   module: the module manufacturer's grant covers the module in isolation,
   but the FCC expects verification that the module still meets its
   fundamental-emission and spurious-emission limits once it's installed
   and operating inside our enclosure, next to our switching regulator and
   sensor wiring. In practice this is usually the same lab visit as the
   unintentional-radiator scan, not a second trip.
3. Self-declare via Supplier's Declaration of Conformity (SDoC) — no FCC
   filing, no Telecom Certification Body review needed for the
   unintentional-radiator side, since the intentional-radiator side is
   already covered by the module's own certification.

**Rough cost/timeline (estimate — confirm with an accredited EMC lab
quote):** a simple digital device's SDoC-path testing runs roughly
$1,500–$5,000, and composite/host verification on top of a pre-certified
module typically adds to the same test session rather than requiring a
separate full RF characterization. Turnaround at a lab is commonly 1–2
weeks once a working, enclosure-final unit is in hand.

**What helps here:** SELV-only board (see [docs/hardware/bom.md](hardware/bom.md)
and Design-for-compliance register below), external UL-listed PSU (removes
the power supply from our EMC/safety scope entirely — that's the
manufacturer's certification, not ours), and using a genuinely
FCC-granted, name-brand radio module rather than an unverified clone.
That last point is not automatic: see the design-for-compliance register
below and the sourcing risk already flagged in
[docs/product-line.md](product-line.md#risks) — "cheap-module supply
variability" is a cost/quality risk today and becomes a compliance risk
the moment a board ships with a radio module that doesn't actually carry
a valid FCC ID.

### UL / NRTL listing

**What it covers:** product safety — fire, shock, and injury hazards —
for the electrical/electronic device as a whole. This is the certification
an AHJ (authority having jurisdiction, i.e. the local electrical
inspector), an insurance underwriter, or a commercial kitchen's own risk
policy is actually asking about when they say "is it listed?"

**What applies here:** the likely standard is **UL 62368-1 / IEC 62368-1**
("Audio/video, information and communication technology equipment"),
which has fully superseded the older UL 60950-1 and UL 60065 as of the
mid-2020s and is the standard low-power networked electronics like this
board fall under. A cord-connected, SELV-only, externally-powered board
inside a plastic enclosure is a straightforward case within that standard
— no line voltage inside the enclosure to evaluate, no battery chemistry
to add scope (see [docs/hardware/bom.md](hardware/bom.md) risk (c) and the
SELV design decision in [docs/safety.md](safety.md)).

**Why NRTL listing matters specifically for this product:** a commercial
kitchen is exactly the environment where "listed" isn't optional in
practice, even where code doesn't strictly mandate it for every accessory
device — health inspectors, fire marshals, and the restaurant's own
property/liability insurer routinely look for a recognizable mark (UL,
ETL/Intertek, or another NRTL) on anything plugged in near food-service
equipment. Without it, an AHJ can refuse occupancy sign-off over an
unlisted device, and an insurer can use it as grounds to deny a claim.
This is a practical sales-enablement requirement as much as a legal one.

**Listing vs. recognition:** *Listing* certifies the complete end product
as sold (what we need). *Recognition* (the "backwards UL" mark) certifies
a component intended to be built into something else — that's what the
external PSU already carries from its own manufacturer, not what we'd
seek for the whole unit.

**Factory surveillance:** once listed, the NRTL runs unannounced factory
follow-up inspections (commonly quarterly) to confirm production units
still match the certified design — same components, same construction.
This is an ongoing cost and an ongoing constraint: swapping a sourced part
(the MCU module, the PSU) after listing means notifying the NRTL, not just
changing the BOM.

**Rough cost/timeline (estimate — confirm with an NRTL quote; UL, ETL, and
CSA are all accepted NRTLs and worth quoting against each other):**
initial certification for a simple, low-power, SELV device in this
product category realistically lands in the **$5,000–$20,000** range —
towards the low end of the commonly-cited $5,000–$50,000 UL range because
there's no battery chemistry and no line-voltage evaluation to add scope.
Annual factory follow-up/surveillance runs roughly $1,500–$3,000/year at
the simple end, though some sources cite $20,000–$30,000/year for more
inspection-heavy programs — this is a case where the estimate needs a
concrete quote before committing to a number in a business plan, not a
figure to hold as fixed. Timeline: expect 6–12 weeks from sample
submission to listing on a first pass, longer if a design revision is
needed after initial test failures.

### NEC (NFPA 70)

**What it governs:** the *installation* of electrical equipment, not the
product's own design or manufacture — NEC applies to what an electrician
or technician does at the site, not what we build at the factory.

**How this product fits:** because Guard/Logger/Live are cord-and-plug
connected (or the equivalent low-voltage-only wiring inside the host
machine) and NRTL-listed, they fall into NEC's normal path for a listed
accessory device — no special permitting burden beyond what any listed
plug-in device would face. The install-guide requirement already in
[docs/safety.md](safety.md) — the logger's power adapter goes into its
own, separate outlet, never tapped off the machine's dedicated circuit —
is directly a good-NEC-citizenship practice: it keeps the monitor's branch
circuit and the machine's branch circuit independently disconnectable,
which is exactly what NEC expects from a device that isn't part of the
listed appliance it's monitoring.

**Article 725 relevance:** the sensor wiring that runs from the core
enclosure to CT clamps, thermocouples, and AC-presence opto taps inside
the host machine's cabinet is low-voltage, current-and-voltage-limited
circuitry — the kind of wiring NEC Article 725 classifies as Class 2
power-limited circuits (the NEC-side analog to the IEC's SELV
classification we already design to). Article 725 sets separation and
routing rules for Class 2 wiring relative to line-voltage conductors
inside the same enclosure or raceway — worth a design/install-guide check
once a permanent-install harness (Guard/Logger) is finalized, since DAQ
Pro's current install procedure already keeps sensor leads dressed away
from line-voltage terminals as general practice
([docs/install-guides/137A.md](install-guides/137A.md)) but hasn't been
checked against Article 725's specific separation distances.

### NFPA generally

NFPA 70 (the NEC, above) is the NFPA document that actually applies here.
One other NFPA standard is worth naming for awareness, not action: **NFPA
96** governs commercial kitchen ventilation and fire suppression for
cooking equipment exhaust systems. It doesn't govern this product, but it
does constrain *where* this product can be installed — nothing about
Guard, Logger, or Live may be mounted in or near a hood/exhaust/grease-duct
zone. That's already consistent with the placement and airflow
requirements in [docs/safety.md](safety.md), and frozen-drink machines
aren't cooking equipment under a hood in the first place, so this is a
one-line awareness note, not an open compliance item. Nothing else in the
NFPA catalog looks applicable to a low-voltage monitoring accessory on
refrigeration equipment.

### NSF/ANSI

The host machines (Frosty Factory 117A/127A/137A) are NSF-listed food
equipment. Installing a third-party device inside one raises two separate
questions, and they are not the same question:

1. **Does frosty-monitor itself need NSF/ANSI 169 certification?**
   NSF/ANSI 169 ("Special Purpose Food Equipment and Devices") covers
   equipment and devices not fully addressed by other NSF food-equipment
   standards. Given the design decisions already in this repo — no
   food-zone contact, no product-contact surfaces, mounted outside or
   away from the food path (see [docs/safety.md](safety.md), "Placement")
   — frosty-monitor likely doesn't perform a food-contact or
   food-processing function that would put it squarely inside 169's
   scope, but "likely" is doing real work in that sentence and this needs
   an actual determination from an NSF-accredited certifier, not an
   assumption in a repo doc.
2. **Does installing frosty-monitor void the host machine's own NSF
   listing, or its manufacturer's warranty?** This is the sharper,
   more practical question, and it's a genuine open business item —
   **flag it, don't guess at it.** Modifying a listed piece of food
   equipment, even non-invasively (clamp-on CTs, external temperature
   probes, no cutting into the food-contact envelope), is exactly the
   kind of thing that can trigger a "field modification voids listing"
   clause depending on how Frosty Factory's own NSF listing and warranty
   terms are written. This needs a direct conversation with Frosty
   Factory (does a monitoring accessory like this affect their listing or
   void a customer's warranty?) and, if their answer is ambiguous, an NSF
   consultant's opinion.

**Be honest about where the real risk sits:** the electrical
certifications above (FCC, UL) are well-trodden paths with predictable
costs and timelines. This NSF/host-manufacturer question is not — it's
the item most likely to surface an unpleasant surprise, and it's also the
cheapest and fastest one to start resolving, since it costs nothing but a
phone call. See the sequenced action plan below for why it's placed
first.

### CE/UKCA

Out of scope until there's a non-US sale — no work needed today, but
worth naming what it would involve so it isn't a surprise later: the
**RED** (Radio Equipment Directive, since there's a radio module),
**EMC** directive, and an **LVD-adjacent** evaluation (Low Voltage
Directive technically applies 50–1000VAC/75–1500VDC and this board is
SELV throughout, but a CE technical file for a radio device still expects
a documented safety rationale covering the SELV design). RED as of the
mid-2020s also pulls in cybersecurity and data-protection requirements
under its delegated act, which adds scope beyond the older EMC/RF-only
expectations. Rough order of magnitude for a comparable low-power
wireless IoT device (estimate — confirm with an EU-recognized notified
body or test lab if/when this becomes real): **€8,000–€15,000** covering
EMC, radio, and cybersecurity assessment plus the technical file, on a
first-pass basis.

### Liability insurance

Certification complements product liability coverage — it does not
replace it. A UL listing and an FCC SDoC on file materially help defend a
claim if something ever goes wrong at a customer site, but they don't
substitute for the coverage itself. The earlier advice to loop in the
insurer stands and applies here specifically: bring the certification
plan to the insurer before it's finished, not after, so their underwriting
requirements (if any) inform the plan instead of forcing a second pass
through it.

## Sequenced action plan

Ordered from today's state to a listed Guard product. All costs are
estimates pending real quotes; ranges are cumulative and rough.

1. **NSF / Frosty Factory host-manufacturer conversation.** Start now —
   costs nothing, takes a phone call and possibly a follow-up email
   thread, and its answer can reshape mounting/install requirements before
   any hardware or cert spend happens. Arguably belongs before item 2 for
   that reason even though it's listed here in build order.
2. **EE design review.** Confirm the production board (not the dev-kit
   prototype) is SELV-clean throughout, confirm the actual radio module
   sourced for production carries a valid FCC grant (not an unverified
   clone — see the design-for-compliance register below), confirm PSU
   selection is itself UL-listed. Internal cost, calendar time only.
3. **Pre-compliance EMC scan.** A cheap early look at emissions before
   committing to accredited lab time — rented chamber/equipment time runs
   roughly **$1,000–$2,000/day** (estimate — get a quote from a local
   pre-compliance test house), one to two days. Catches gross EMC
   problems (bad grounding, an unshielded high-speed trace) while they're
   still cheap to fix.
4. **FCC SDoC testing (unintentional radiator + composite/host
   verification).** Accredited EMC lab, **$1,500–$5,000** (estimate).
   1–2 weeks turnaround once a final-enclosure unit is ready.
5. **NRTL submission (UL/ETL/CSA — quote at least two).** **$5,000–
   $20,000** initial (estimate), 6–12 weeks to listing on a clean first
   pass. This step wants the FCC-tested, EE-reviewed hardware revision
   going in, not an earlier prototype — a design change after NRTL
   submission means resubmitting.
6. **Insurer review.** Bring the certification package (FCC SDoC file,
   NRTL listing, this roadmap) to the liability insurer once items 1-5 are
   either complete or far enough along to show a credible plan.

**Rough cumulative cost (estimate, Guard-scale, first product through the
process):** roughly **$8,000–$30,000** in direct test/certification spend,
excluding annual NRTL surveillance fees (**$1,500–$3,000+/year**,
ongoing) once listed. **Rough calendar time:** 3–6 months from a
production-ready board to a listed product, assuming no major redesign is
forced by a failed test — the NSF conversation (item 1) can and should run
in parallel with items 2-4, not block them.

## Design-for-compliance register

Concrete rules the hardware has to keep obeying so a future PCB revision
doesn't silently break the path laid out above. This is a living
checklist — anyone touching the board design should check against it
before a revision ships.

| Rule | Why it matters for compliance | Where it's already established |
|---|---|---|
| SELV-only inside the enclosure — no line voltage ever present on the board or its connectors | Keeps the product inside UL 62368-1's SELV evaluation path instead of triggering full line-voltage safety analysis; keeps CE's LVD exposure minimal if that day comes | [docs/safety.md](safety.md), "Only low-voltage DC inside the logger enclosure" |
| External, independently UL-listed PSU — power conversion never happens on our board | The PSU's own listing covers the highest-risk safety evaluation (mains isolation, overcurrent, thermal); our board inherits none of that scope | [docs/hardware/bom.md](hardware/bom.md) — "UL-listed 5V/3A USB-C wall adapter" |
| Radio module must carry a genuine, verifiable FCC grant (and CE/RED grant if that day comes) — not an unverified clone board | Modular approval is what keeps FCC compliance cheap; a clone module without a real grant forces full intentional-radiator testing from scratch and can mean the product was sold non-compliant | Not yet enforced in sourcing — flagged here and in [docs/product-line.md](product-line.md#risks) ("cheap-module supply variability") as a real gap to close before production sourcing is locked |
| Antenna keep-out zone respected in enclosure and chassis-mounting design | Both FCC composite testing and RF performance assume the module's integration guide (antenna clearance from metal) was followed; violating it can fail composite testing or degrade range | [docs/product-line.md](product-line.md), Tier 4 "Antenna-conscious enclosure delta" |
| ESD protection on every externally-accessible connector (sensor leads, card slot, USB) | Required by both UL 62368-1's ESD immunity expectations and basic field reliability | Not yet a documented board-level rule — add to the next EE design review (see action plan item 2) |
| No food-zone contact, no surface in the food-product path | Keeps frosty-monitor out of NSF/ANSI 169's food-contact scope and off the "voids the host's NSF listing" concern's worst case | [docs/safety.md](safety.md), "Placement" |
| Labeling: FCC compliance statement (SDoC-path device, no FCC ID needed on our board itself, module's own FCC ID stays visible per its integration guide) | Required marking for a marketed digital device under Part 15 | Not yet implemented — add to production label artwork once FCC testing (action plan item 4) is complete |
| Labeling: NRTL listing mark placement, per the listing NRTL's marking requirements | Required to actually claim the listing in the field | Not yet implemented — NRTL will specify exact placement/size as part of listing (action plan item 5) |
| Labeling: electrical ratings label (input voltage/current, SELV designation) | Standard requirement for a listed electrical accessory; also what an inspector or insurer looks for first | Not yet implemented — add alongside the above |

## Cross-links

- [docs/product-line.md](product-line.md) — the four-tier structure this
  roadmap targets (sold products: Guard, Logger, Live) versus DAQ Pro's
  lighter, business-owned-tool posture.
- [docs/safety.md](safety.md) — the install-time safety practices this
  roadmap builds on: SELV-only enclosure, separate-outlet power, no
  food-zone contact, panel/airflow/heat handling.
- [pcb/guard/README.md](../pcb/guard/README.md) — Guard's PCB design,
  where the design-for-compliance register above becomes concrete
  schematic and layout decisions (forward reference — this file is being
  built concurrently with this roadmap).
