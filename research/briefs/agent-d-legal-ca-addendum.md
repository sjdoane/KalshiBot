# Agent D Addendum: California-Specific Legal/Tax Overlay for Project Kalshi

**CA Hard-Block Status = OPEN (cleaner than WA today, but AG action is loaded and chambered)**

> **Disclaimer.** Research summary, not legal or tax advice. Consult a CA-licensed attorney and a CPA before live trading. Picture is moving weekly. No em-dashes per project hard constraint. Author is not a lawyer.

As of 2026-05-22, a CA-resident retail user can open, fund, and trade on Kalshi including sports event contracts. CA is NOT on Kalshi's geo-block list (AZ, IL, MA, MD, MI, MT, NV, OH; NJ also blocked for sports). The federal preemption argument has so far held in CA federal court. However, (a) the Ninth Circuit appeal by three CA tribes is pending with amici from 27 state AGs (CA on the tribes' side), (b) AG Rob Bonta is reportedly preparing a cease-and-desist and possible state suit per CNIGA chair James Siva (Dec 2025), and (c) the May 2026 Ninth Circuit decision in the WA remand case cut against Kalshi on the preemption question that protects CA access. CA is the cleaner state to trade from today, but the surface area is larger and the political opposition is stronger than WA.

---

## 1. CA Kalshi Access Status (current)

- **Account/funding.** No geo-block on CA. Signup, KYC, and ACH funding work normally for a CA residential address. CFTC-regulated DCM status is the basis for access.
- **Sports contracts.** Available to CA users. Over $240M in Super Bowl LX trading volume on Kalshi documented (Feb 2026). College and pro CA-team markets are tradable.
- **CA agency actions to date.** No published cease-and-desist from CA DOJ, the Bureau of Gambling Control (within DOJ), or the California Gambling Control Commission (CGCC) to Kalshi as of 2026-05-22. This contrasts with NJ DGE, NY State Gaming Commission, CT DCP, MA AG, NV GCB, RI AG, OH Casino Control Commission, IL Gaming Board, MI Gaming Control Board, and WA AG, all of which have issued letters or filed suit.
- **CA AG posture.** Bonta has joined the multistate amicus coalition (38 AGs, April 2026, against CFTC exclusive-jurisdiction position in the MA SJC matter). Per CNIGA chair Siva (Dec 2025), Bonta is "preparing a cease-and-desist" and "considering" a state suit. Bonta's office did not confirm. Treat as imminent-but-uncertain.

## 2. Tribal IGRA Exposure in California

- **CA tribal case.** Blue Lake Rancheria, Chicken Ranch Rancheria of Me-Wuk Indians, and Picayune Rancheria of the Chukchansi (filed July 2025, N.D. Cal., Judge Jacqueline Scott Corley). Plaintiffs sought to enjoin Kalshi sports contracts on IGRA Class III grounds.
- **Nov 2025 ruling.** Court DENIED preliminary injunction. Held UIGEA and CEA, not IGRA, govern Kalshi event contracts; only the CFTC can rule a contract violates the CEA.
- **Ninth Circuit appeal.** Tribes appealed. The AGA and 27 state AGs filed amici (Jan 2026) supporting tribes. On 2026-05-06, the Ninth Circuit DENIED the tribes' motion to consolidate the CA appeal with the NV prediction-market appeal, keeping the cases on separate tracks. Argument timing not yet calendared.
- **WI parallel (cautionary).** 2026-05-11, U.S. District Judge William M. Conley (W.D. Wis.) issued the first federal ruling siding with tribal IGRA plaintiffs (Ho-Chunk Nation). This is the first crack in Kalshi's federal litigation record. Persuasive but not binding on the Ninth Circuit.
- **Geofencing question.** Kalshi does NOT currently geofence CA tribal lands; the Nov 2025 ruling found no IGRA hook. Bot recommendation: do NOT operate the bot from a tribal-land Wi-Fi network (Cabazon, Pechanga, Morongo, Agua Caliente, San Manuel, Yaamava' etc.). Even though Kalshi takes the position no geofence is required, an active suit makes any tribal-land trade a needless evidentiary exhibit. The bot should also check coarse IP/geolocation and pause trades if it detects routing through a tribal-land network.

## 3. CA Physical-Location vs WA Domicile

- **Which state's law applies?** Kalshi makes the state-restriction call based on the residential address on file at KYC. A WA-domiciled user with WA on Kalshi's records is, from Kalshi's perspective, a WA user even when sitting in LA. WA litigation risk follows the account.
- **State-law claims for criminal liability against the user.** Both WA (RCW 9.46) and CA (Penal Code 330 et seq., 337a for bookmaking/sports wagering) criminalize unauthorized gambling. PC 337a targets bookmakers and pool operators, not individual bettors; the bettor side is typically a low-level infraction (PC 337). No public record exists of any state going after an individual retail user (vs. the platform) for trading event contracts. Enforcement risk is at the platform level, not the user level.
- **CA enforcement risk against the user.** Effectively nil at $100 cap. Even at scale, the practical posture is that the state goes after Kalshi; the user is a third-party customer.
- **Forward-looking principle.** If the operator later moves to a Kalshi-restricted state (NV, IL, etc.) while still WA-on-file, Kalshi's terms forbid trading from a restricted state regardless of domicile. The bot should fail-safe stop trading if it detects an IP geolocated to a restricted state.

## 4. CA Tax Overlay

- **Resident vs nonresident determination.** CA taxes residents on worldwide income. R&TC 17014 defines "resident" as anyone in CA for other than a temporary or transitory purpose, plus anyone domiciled in CA who is outside the state temporarily. Cal. Code Regs. 17016 codifies the 9-month presumption: more than 9 months in CA in a tax year = presumed resident (rebuttable).
- **Student-specific rule.** Out-of-state students attending a CA school do NOT automatically become CA residents (and vice versa). Facts-and-circumstances test: WA driver's license, WA voter registration, WA bank, WA permanent address, family in WA, returns to WA on breaks all cut toward continued WA domicile. A USC undergrad on a 9-month academic calendar who summers in WA can credibly maintain WA domicile.
- **Likely posture.** If the operator is at USC Aug-May and home in WA Jun-Jul, time in CA is ~9-10 months and the 17016 presumption is on the edge. Practical default for CA-FTB is to file Form 540NR (Part-Year or Nonresident) reporting CA-source income only. Kalshi P/L is intangible income; under sourcing rules, intangible income of a nonresident is sourced to the state of residence (WA), so it is NOT CA-taxable for a nonresident.
- **If treated as a CA resident.** Worldwide income taxed by CA. Top marginal bracket 13.3% (over $1M); 9.3% kicks in around $68K single, 11.3% around $375K. Capital gains taxed as ordinary income. CA does NOT allow gambling-loss deductions to exceed winnings even as an itemized deduction (FTB conforms to federal but does not have OBBBA's 90% cap baked in either, so check FTB conformity legislation late 2026). If event contracts are characterized as gambling for federal purposes, CA follows that characterization.
- **Dollar exposure at $100 cap.** Trivial. Even at $1,000 PnL net, CA tax is $93 to $133. Document for scaling; do not let it gate Phase 1.5.
- **Filing trap.** If the operator IS a CA resident in the FTB's view but files only a WA federal return, that is a CA non-filing exposure for 4 years (FTB lookback). Worth a 20-minute CPA call before scaling beyond ~$5k of annual PnL.

## 5. Address-on-File Recommendation

- **Two candidate addresses.** (a) WA family address (parents' home). (b) CA dorm or apartment near USC.
- **WA address (status quo).** Pros: maintains WA domicile narrative for tax. Cons: subjects the account to whatever the WA AG suit delivers. If a WA-resident geofence or restitution order lands, the account is in scope. Kalshi could freeze WA-resident deposits.
- **CA address (USC dorm/apartment).** Pros: today CA is unrestricted with no state cease-and-desist; account would not be in WA AG suit's class definition. Cons: (i) once Bonta acts, the CA exposure flips and likely faster than WA's because CA AG has broader resources; (ii) creates a CA-residency factor for FTB even if the operator's domicile remains WA; (iii) Kalshi T&Cs require accurate residential address; updating mid-stream is fine but providing CA when WA is the true domicile is a misrepresentation risk.
- **Recommendation (research, not advice).** If the operator genuinely lives in a CA dorm/apartment Aug-May, that IS their residential address by ordinary meaning and is a defensible Kalshi KYC entry. Use the CA dorm address only if the operator is actually living there and only as long as that remains true. Update Kalshi when moving back to WA for the summer if Kalshi's terms require it (most platforms require updates within 30 days). Do NOT use a CA address purely to dodge WA litigation while domiciled elsewhere. The CA-address option meaningfully reduces near-term mid-project shutdown risk at the cost of slightly higher CA FTB exposure and a (still imminent-but-uncertain) future CA AG action.
- **Hybrid play.** Keep the account on the address that genuinely matches current physical residence at signup. If that is CA (likely, given USC), register CA. The CA AG threat is not yet operational; the WA AG suit IS operational. Net: CA registration likely lower mid-project shutdown risk than WA registration as of 2026-05-22.

## 6. CA Pending Actions to Monitor (6-12 months)

- **CA AG Bonta cease-and-desist / suit.** Per CNIGA Dec 2025, "preparing." Could land any week. Watch oag.ca.gov/news.
- **Ninth Circuit, Blue Lake Rancheria v. Kalshi appeal.** Briefing 2026; oral argument not yet set as of May. Reversal would re-open IGRA injunction risk and likely force Kalshi to geofence tribal lands; could also push CA AG to act.
- **Ninth Circuit, WA case.** Already remanded to state court May 2026. WA state court hearings on injunction expected summer 2026. A WA injunction would be a strong signal CA is next.
- **AB 1840 (CA Assembly).** Bans public officials from trading on inside info; narrow scope, low operator impact, but signals CA legislature is engaged with the space.
- **CFTC ANPRM final rule on event contracts.** Comments closed 2026-04-30; final rule timeline Q3-Q4 2026. A restrictive CFTC rule could moot state-law fights but also shut down sports contracts nationally.
- **California Nations Indian Gaming Association (CNIGA) lobbying.** Active and well-funded. CNIGA and California Tribal Business Alliance are pushing the legislature and the AG. Watch CNIGA press releases.
- **Federal Schiff/Curtis bill.** Would let states regulate prediction markets directly. If it advances, CA gets explicit authority to ban Kalshi.

---

## Sources

- "Is Kalshi legal in California?" defirate.com, Feb 8 2026: https://defirate.com/news/is-kalshi-legal-in-california/
- "How Kalshi win in California court sets up for future prediction market battles," iGamingBusiness, Nov 2025: https://igamingbusiness.com/innovation/kalshi-california-prediction-markets-court-case/
- "California Tribes Fail in Attempt to Stop Kalshi's Sports Event Contracts," GamblingNews, Nov 2025: https://www.gamblingnews.com/news/california-tribes-fail-in-attempt-to-stop-kalshis-sports-event-contracts/
- "Ninth Circuit Splits Kalshi Prediction Markets Appeals," SCCG Management, May 13 2026: https://sccgmanagement.com/sccg-articles/2026/05/13/ninth-circuit-denial-fragments-west-coast-cea-challenges/
- "California AG Poised to Target Prediction Markets, CNIGA Chair Says," CasinoBeats, Dec 11 2025: https://casinobeats.com/2025/12/11/california-ag-prediction-markets-lawsuit-cniga/
- "California Attorney General Rob Bonta to target prediction markets," ReadWrite, 2025/2026: https://readwrite.com/california-attorney-general-prediction-markets/
- "Siva: California Attorney General Prepping To Act Against Prediction Markets," InGame: https://www.ingame.com/california-attorney-general-prediction-markets/
- "38 State Attorneys General Back Massachusetts Against Kalshi," Bettors Insider, Apr 28 2026: https://bettorsinsider.com/sports-betting/2026/04/28/38-attorneys-general-just-lined-up-against-prediction-markets-while-the-cftc-takes-the-fight-to-the-massachusetts-supreme-court/
- "Judge Allows Ho-Chunk Lawsuit Against Kalshi to Proceed," Covers, May 12 2026: https://www.covers.com/industry/judge-allows-ho-chunk-lawsuit-against-kalshi-to-proceed-wisconsin-may-12-2026
- "Kalshi, Polymarket lose bids to halt Nevada and Washington gambling cases," The Block, May 2026: https://www.theblock.co/post/402397/kalshi-polymarket-lose-bids-to-halt-nevada-and-washington-gambling-cases
- "Washington sues Kalshi," CoinDesk, Mar 28 2026: https://www.coindesk.com/policy/2026/03/28/washington-sues-kalshi-as-states-ramp-up-legal-pressure-against-prediction-markets
- "Where is Kalshi Legal?" SaturdayDownSouth, May 2026: https://www.saturdaydownsouth.com/prediction-markets/kalshi-promo-code/legal-states/
- Cal. Code Regs. tit. 18, sec. 17014 (resident definition): https://www.law.cornell.edu/regulations/california/18-CCR-17014
- Cal. Code Regs. tit. 18, sec. 17016 (9-month presumption): https://www.law.cornell.edu/regulations/california/18-CCR-17016
- FTB Publication 1031 (2024 Guidelines for Determining Resident Status): https://www.ftb.ca.gov/forms/2024/2024-1031-publication.pdf
- CA Penal Code sec. 337a: https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=PEN&sectionNum=337a
- CA FTB Gambling Income: https://www.ftb.ca.gov/file/personal/income-types/gambling.html
- Kalshi KYC requirements: https://help.kalshi.com/en/articles/13823782-what-information-is-required-to-verify-my-kalshi-account
- "State Lawmakers Are Trying to Rein in Prediction Markets," Covers, Mar 2026: https://www.covers.com/industry/prediction-markets-state-legislatures-introduce-bills-sports-betting-march-2026
- "California tribes gather to combat encroachment of prediction markets," CDC Gaming: https://cdcgaming.com/california-tribes-gather-to-combat-encroachment-of-prediction-markets/

---

## Unknowns

- Exact timing of any CA AG Bonta cease-and-desist or suit. CNIGA telegraphed it Dec 2025; nothing public on AG OAG website as of 2026-05-22.
- Whether Kalshi's residency-update flow requires proactive notice when a user moves states, or only on next KYC refresh. Kalshi help center is silent.
- Whether the Ninth Circuit will hear the CA tribal appeal en banc or in panel; argument not yet calendared.
- FTB's specific characterization of Kalshi P/L (capital, ordinary, gambling) for CA tax purposes. No published FTB guidance.
- Whether Kalshi has a CA-specific geofence on tribal land IPs internally even though it disclaims the legal duty. No public confirmation either way.
- Whether the operator's actual time-in-CA crosses the 9-month line in calendar 2026; depends on USC academic calendar and summer plans.
- Behavior of Kalshi's KYC system if a user has WA on file and connects from a CA dorm IP for months. Likely tolerated (many users travel), but no documented policy.
- Whether any pending CA Assembly bill beyond AB 1840 would impose user-side restrictions; legislative session live through Sep 2026.
