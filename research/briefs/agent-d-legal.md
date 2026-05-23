# Agent D Brief: Legal, Tax, and Regulatory Considerations for a WA Resident on Kalshi

> **Disclaimer.** This is a research summary only, not legal or tax advice. The author is not a lawyer or CPA. Consult a licensed Washington attorney and a CPA familiar with derivatives/prediction-market taxation before live trading. The regulatory picture is moving weekly as of May 2026; revalidate before risking real capital.

> **NO em-dashes used in this file per project hard constraint.**

---

## Headline: Hard-Block Status = UNCLEAR (leaning ACCESSIBLE, with elevated risk)

As of 2026-05-22, a Washington resident can still open, fund, and trade on Kalshi. There is no preliminary injunction in force halting WA access. However, the State of Washington is actively litigating to shut Kalshi down for WA residents (filed 2026-03-27, King County Superior Court, remanded from federal court). Sports event contracts in particular are the focus of the litigation and the WA State Gambling Commission's 2025-12-12 advisory declaring prediction markets "unauthorized activity." Material risk of mid-project loss of access (account freeze, deposit reversals, or geofence) within 3 to 12 months. The user should treat this as a soft block: trading is possible today, but the legal cloud is genuine and the bot must be built to wind down quickly.

---

## 1. Kalshi Access in Washington State (Lead Section)

**Can a WA resident open and fund an account today?** Yes. As of 2026-05-22 Kalshi's signup flow does not geo-block Washington. Kalshi's own state-availability lists (cited across third-party trackers in May 2026) place WA in the "fully supported" category, not the restricted nine (AZ, IL, MA, MD, MI, MT, NJ, NV, OH). Sports contracts are available to WA residents on the platform notwithstanding the pending state lawsuit.

**WA enforcement timeline:**
- **2025-12-12.** WA State Gambling Commission posted an advisory declaring online event-based contracts "unauthorized activity" in WA. Characterized as precautionary, not a cease-and-desist. Did not name Kalshi directly but covered DCMs offering event contracts.
- **2026-03-27.** WA Attorney General Nick Brown filed civil suit in King County Superior Court against Kalshi. Counts: violation of WA Gambling Act (RCW 9.46) and Consumer Protection Act. Relief sought: permanent injunction, restitution to WA residents, disgorgement of Kalshi profits from WA, civil penalties per violation.
- **2026-04 onward.** Kalshi removed to federal court; U.S. District Judge John C. Coughenour remanded the case back to state court holding gambling regulation is a state issue. Kalshi appealed and sought stay.
- **2026-05 (mid-May).** Ninth Circuit panel denied Kalshi's and Polymarket's bids to block lower-court rulings, sending the cases back to state court. No preliminary injunction is yet in place against Kalshi in WA.
- No court hearings on the merits or injunction were scheduled as of early April 2026 per WA State Standard reporting.

**Practical implication.** Trading is currently mechanically possible from WA. The bot must assume one of these can happen with little notice: (a) preliminary injunction granted in King County, (b) Kalshi voluntarily geofences WA, (c) deposits held / withdrawals delayed pending escheatment or court-ordered freeze, (d) sports markets specifically blocked for WA while non-sports remain. The bot's risk module should monitor for this and trigger a wind-down.

**Holds/restrictions specific to WA.** None publicly documented as of 2026-05-22 beyond the litigation. Ordinary Kalshi deposit/withdrawal mechanics apply.

---

## 2. Federal Regulatory Context

- **Kalshi's status.** KalshiEX LLC is a CFTC-registered Designated Contract Market (DCM). Federally legal as a derivatives venue; the dispute is whether that federal status preempts state gambling law for sports-themed event contracts.
- **Election contracts.** Kalshi won at D.C. district court in 2024; the CFTC dropped its appeal in May 2025 under the new administration. Election event contracts are now offered.
- **Sports event contracts.** Kalshi expanded into sports in January 2025. Split federal record as of May 2026:
  - **Third Circuit (NJ), 2026-04-06.** First federal appellate ruling: CEA preempts state gambling laws as applied to Kalshi sports contracts on a CFTC DCM. Kalshi won.
  - **Nevada district court, 2026-03.** TRO and extended injunction against Kalshi's sports products in NV; Kalshi sidelined for sports in NV.
  - **Ninth Circuit, oral argument 2026-04-16.** Consolidated Kalshi/Robinhood/Crypto.com cases against NV Gaming Control Board. CFTC filed amicus asserting exclusive jurisdiction. Outcome pending. This ruling will directly bind WA federal courts in the Ninth Circuit and is the single most important pending event for the user.
- **CFTC rulemaking.** 2026-03-16 the CFTC issued an Advance Notice of Proposed Rulemaking (ANPRM) on event contracts; comments closed 2026-04-30. Replaces withdrawn 2024 rules. CFTC Chair Michael Selig testified 2026-04-16 in support of allowing sports event contracts as financial instruments. Final rule timeline unclear but could land Q3/Q4 2026.
- **Tribal and Congressional pushback.** 60+ tribes filed amicus briefs; New Mexico pueblos sued Kalshi in May 2026 alleging IGRA violations and demanding geofencing of tribal lands. Democratic members of Congress urged CFTC restrictions on sports event contracts (CNBC, 2026-04-30). At least one congressional bill is reportedly in play to clarify CFTC event-contract jurisdiction.

**Bottom line for the bot.** A Supreme Court split is plausible. A circuit-split holding against Kalshi could remove sports markets nationally; an unfavorable Ninth Circuit ruling could pull sports specifically from WA residents.

---

## 3. Tax Treatment for an Individual Trader

**This is the single most ambiguous area in the brief. CPAs disagree. No IRS Revenue Ruling, Private Letter Ruling, or formal FAQ resolves event-contract classification as of 2026-04-30.**

**1099 forms Kalshi actually issues:**
- **1099-INT** if interest earned on cash balances reaches $10+.
- **1099-MISC** for referral bonuses and credits. Threshold raised to $2,000+ for tax year 2026 (was $600 in 2025).
- **1099-B** Kalshi's coverage is limited. Some sources (PredScope, marketmath.io) claim Kalshi sends 1099-B for proceeds exceeding $600; others (Camuso CPA, Monaco CPA) state Kalshi does NOT issue a comprehensive 1099-B covering event-contract acquisitions, dispositions, basis, or P/L. Conservative posture: assume the bot must compute and reconcile its own P/L; do not rely on Kalshi 1099-B coverage to be complete.

**Possible federal treatments (all three defensible, none IRS-blessed):**
1. **Section 1256 contracts (60/40 split, mark-to-market at year-end).** Aggressive. Argument: Kalshi is a CFTC DCM. Counter-argument: event contracts are not enumerated in IRC 1256 (regulated futures, foreign currency, non-equity options, dealer equity options, dealer securities futures), and binary event contracts arguably do not satisfy the daily-mark-to-market requirement. If claimed, file Form 6781, flow to Schedule D. Wash-sale exempt if 1256 applies.
2. **Capital gains (short-term, since contracts typically resolve in days or weeks).** Moderate. Treat each contract as property; report on Form 8949 / Schedule D. Net losses capped at $3,000/year against ordinary income with indefinite carryforward.
3. **Ordinary income / loss (Schedule 1 line 8 or Schedule C if trader-status).** Most conservative; lowest audit risk. No favorable rate.
4. **Gambling income (Schedule 1 line 8b, losses only via Schedule A itemized).** Treatment WA state and several other states are pushing for. Trap: under the One Big Beautiful Bill Act (OBBBA), gambling-loss deductibility is capped at 90% of total losses starting tax year 2026. A break-even $50k-win / $50k-loss trader could face $5k+ phantom taxable income, especially taking the standard deduction. Worst option for an active bot.

**Recommendation for the bot's bookkeeping module.** Log every trade with enough fields to support any of the four treatments later. Have the user pick the treatment in consultation with a CPA before April 2027 filing. See action items in summary.

**Wash-sale rule (IRC 1091).** Section 1091 applies only to "stock or securities." Kalshi event contracts are not stock or securities; they are derivatives/contracts. Most analyses conclude 1091 does not apply. If 1256 treatment is elected, wash-sale is statutorily inapplicable. Confirm with CPA but bot likely does not need wash-sale guarding.

**Washington state tax:**
- WA has no broad personal income tax.
- WA capital gains tax (RCW 82.87, passed 2021, upheld 2023): 7% on LONG-TERM capital gains above the indexed threshold (approximately $278k for 2025, 2026 threshold pending DOR). Tiered: 9.9% above $1M. Kalshi contracts almost always resolve in under one year, so short-term capital gains and ordinary income are not within scope. Plus the $278k floor means at the $100 project cap WA state capital gains tax is not a real concern. Document only.
- WA B&O tax could theoretically reach trader-status returns; not realistic at this dollar size.

**Estimated tax.** At a $100 bankroll, federal estimated-tax safe harbor is not in play. Document the bookkeeping the bot must produce anyway so the same code scales if bankroll grows.

---

## 4. KYC/AML and Account Mechanics

- **Eligibility.** 18+, US resident. Kalshi help center explicitly disclaims providing individual eligibility advice and pushes responsibility to the user.
- **Required at signup.** Full legal name, date of birth, residential address (no PO boxes), Social Security Number. Kalshi is required by CFTC/FinCEN rules to collect SSN for KYC and tax reporting.
- **ID verification.** Government photo ID (driver's license or passport), clear originals (not photos of screens). Address must match.
- **Approval time.** Typically instant; up to 24 to 48 hours if manual review triggered.
- **Deposit methods.** ACH bank transfer (free, 1 to 3 business days settlement), debit card, wire. Plaid used for ACH linkage.
- **Deposit holds.** Portion may be credited immediately; remainder available after settlement.
- **Withdrawal mechanics.** ACH withdrawals free, typically 3 to 4 business days. Debit-card withdrawals capped at $2,500/day. ACH withdrawals not publicly capped.
- **Withdrawal after first deposit.** If withdrawing to the same instrument, funds available once deposit settles. Different instrument: available 2 days after settlement (security hold).
- **Minimum deposit.** None published; can fund with a few dollars. Fits a $50 starting bankroll.
- **Account tiers.** Not clearly documented as differentiated for a US individual account in public materials; verification is binary (verified vs. unverified). Institutional and pro-tier accounts exist but are not in scope.

---

## 5. Pending State and Federal Challenges (next 6 to 12 months)

**Highest risk to WA access:**
1. **WA AG v. Kalshi (King County Superior Court).** Watch for preliminary injunction motion. If granted, WA residents lose access immediately. No hearing scheduled as of early April 2026.
2. **Ninth Circuit ruling on Kalshi/Robinhood/Crypto.com v. Nevada Gaming Control Board.** Oral argument 2026-04-16, opinion pending. Adverse ruling for Kalshi could embolden WA court and trigger voluntary withdrawal from WA by Kalshi.
3. **CFTC final rule on event contracts.** ANPRM comments closed 2026-04-30. Final rule could clarify sports event contract status nationally; could also restrict.
4. **Tribal lawsuits (NM pueblos, CA Blue Lake Rancheria) under IGRA.** Could force national geofencing of tribal lands. WA has tribal gaming compacts; an adverse ruling could be cited by WA AG.

**Other state actions to track (cumulative risk indicator):** Rhode Island sued Kalshi 2026-05-22. Kentucky and New Mexico filed in May 2026. Earlier cease-and-desist letters from IL, MT, NV, NJ, OH (2025), plus AZ, MA, MD, MI added to restricted list. The trend is more states acting, not fewer.

**Congress.** Pending legislation reportedly clarifying CFTC event-contract jurisdiction. Status unsettled. Could go either direction.

---

## Sources

State and Kalshi-WA specific:
- WA AG Press Release, "Washington sues online betting platform Kalshi for illegal gambling," 2026-03-27. https://www.atg.wa.gov/news/news-releases/washington-sues-online-betting-platform-kalshi-illegal-gambling
- CoinDesk, "Washington sues Kalshi as states ramp up legal pressure," 2026-03-28. https://www.coindesk.com/policy/2026/03/28/washington-sues-kalshi-as-states-ramp-up-legal-pressure-against-prediction-markets
- Yogonet, "Washington State Gambling Commission flags event-based contracts as unauthorized," 2025-12-12. https://www.yogonet.com/international/news/2025/12/12/116746-washington-state-gambling-commission-flags-eventbased-contracts-as-unauthorized-raises-concerns-for-operators
- The Block, "Kalshi, Polymarket lose bids to halt Nevada and Washington gambling cases," mid-May 2026.
- Spokesman-Review, "Washington AG alleges Kalshi is in 'direct violation' of state gambling laws," 2026-03-27.
- Seattle Times, "Kalshi 'prediction market' violates WA antigambling laws, AG says," 2026.
- World Law Digest, "Is Kalshi Legal in Washington State?" (cited as available May 2026).
- SaturdayDownSouth, "Where is Kalshi Legal in the U.S.? Full State-by-State Guide (2026)" (WA listed as fully supported).

Federal regulatory:
- Holland & Knight, "Federal Appeals Court: CFTC Jurisdiction Over Sports Event Contracts Likely Exclusive," 2026-04 (Third Circuit ruling 2026-04-06).
- Sidley Austin, "U.S. CFTC Issues Guidance, Advance Notice of Proposed Rulemaking Regarding Prediction Markets," 2026-03.
- Lowenstein Sandler, "CFTC Seeks Input on Prediction Markets," 2026.
- Yogonet, "CFTC drops appeal in Kalshi election betting case," 2025-05-06.
- Venable LLP, "Nevada Court Issues TRO Against Kalshi as Congress Moves to Restrict Event Contracts," 2026-03.
- Stinson LLP, "Sportsbooks or Commodity Exchanges? The Rising Legal Tensions."
- CNBC, "Democrats urge CFTC to rein in prediction markets sports betting," 2026-04-30.
- Cahill Gordon, "Disagreement Deepens Among Federal Courts Over Whether Sports Event Contracts Are Subject to State Regulation," 2025-12-19.

Tax:
- Monaco CPA, "Kalshi, Polymarket & Robinhood Taxes 2026." https://www.monacocpa.cpa/post/prediction-market-taxes-kalshi-polymarket-robinhood
- Camuso CPA, "Kalshi Tax Reporting: What Your 1099 Leaves Out." https://camusocpa.com/kalshi-tax-reporting/
- Camuso CPA, "Section 1256 And Prediction Markets: Do Kalshi And Event Contracts Qualify?" https://camusocpa.com/section-1256-prediction-market-tax/
- PredScope, "Kalshi Taxes: How to Report Event Contract Gains (2026 Guide)." https://predscope.com/guide/kalshi-taxes
- Market Math, "Kalshi 1099: Tax Reporting for Event Contracts." https://marketmath.io/blog/kalshi-1099-guide
- WA Department of Revenue, "Capital gains tax" and "New tiered rates for Washington's capital gains tax."

Account mechanics:
- Kalshi Help Center, "Signing Up as an Individual." https://help.kalshi.com/en/articles/13823778-signing-up-as-an-individual
- Kalshi Help Center, "What information is required to verify my Kalshi account?" https://help.kalshi.com/en/articles/13823782-what-information-is-required-to-verify-my-kalshi-account
- Kalshi Help Center, Transfers FAQ, Bank Deposits, Bank Withdrawals, Security Holds.
- Kalshi Fee Schedule (February 2026). https://kalshi.com/docs/kalshi-fee-schedule.pdf

---

## Unknowns / Blockers

1. **Will WA AG obtain a preliminary injunction?** Unknown. No hearing scheduled as of early April 2026. Could land any time in Q3 2026.
2. **Will Kalshi voluntarily geofence WA?** Unknown. They have not done so to date despite the lawsuit, but a Ninth Circuit loss could change that.
3. **Section 1256 vs ordinary income vs capital gains vs gambling: which is correct?** Federally unresolved. The user MUST consult a CPA before filing 2026 taxes. The bot must log enough data to support any treatment.
4. **Does Kalshi actually issue a 1099-B covering event-contract P/L?** Sources conflict. Treat as if it does not; the bot computes its own P/L authoritatively.
5. **OBBBA 90% gambling-loss cap.** Confirmed for 2026 forward. Active-trading bot is particularly vulnerable if gambling treatment is forced by IRS or state. Plan accordingly.
6. **WA capital gains tax** likely not in scope at $100 bankroll but document.
7. **Will Ninth Circuit issue its ruling within the project's active window?** Possible Q3 2026. The bot should monitor.
8. **Personal jurisdiction-shift risk:** if the user travels out of WA and trades, federal/state nexus changes. The bot's geolocation logging matters for tax residency.
9. **Tribal IGRA lawsuits** could force tribal-land geofencing. The user should not trade while physically on tribal land in WA (Muckleshoot, Tulalip, etc.).
10. **AML reporting / Form 8300 / FBAR.** Not applicable at $100 cap; flag if bankroll ever crosses $10k.
