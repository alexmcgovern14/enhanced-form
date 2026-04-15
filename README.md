User need
=========

Form repeatedly comes up as main information users are looking at pre-game when considering a bet, for example 4/4 interviews here [https://app.usertesting.com/workspaces/1041815/study/5539383/sessions](https://app.usertesting.com/workspaces/1041815/study/5539383/sessions)

Form currently provides the last 5 results for each team, containing W/D/L, score, home/away and opposition.

Users want to go deeper with two main points:

1.  **Was the score representative of the match?** Eg a team can have 20 shots and 6.0 xG but only win 1-0, and equally a team can be dominated and scrape a lucky 1-0 win. Users are clicking through to each game to view the match statistics as an underlying determination of form, as the score is not enough and can be misleading

2.  **Opposition strength: Who were the opposition?** Beating the bottom 5 teams in the league is less impressive than beating the best 5 teams in the league. Users spoke about clicking through to each game and then table, to see the relative situation of the team who the result was against


To solve this some users say they are clicking from form component into each SEV to look at stats (representative score) and table (opposition strength) etc, and then back to the form widget, repeatedly until they’ve looked at each game.

This epic is to find a more efficient way of providing this information to users.

Prototyped solution
===================

Have been testing a prototype to understand what data will be useful to solve these user needs.

The system is designed as a chain, split into stages to be auditable. Description is below, repo here [https://github.com/alexmcgovern14/enhanced-form](https://github.com/alexmcgovern14/enhanced-form)

UI
--

Design has not been properly considered, I’m sure there’s many ways to present this information! Below view (`form_viewer.html`) contains:

*   User can **switch btwn combined and** **home/away** form

    *   **combined** = shows last 5 games for each team at any location.

    *   **Home/away** = shows home team’s last 5 home games and away team’s last 5 away games

*   **Strength rating of opposition** as a number on pill

*   **GenAI summary of form.** Note: this can be any shape and length! needs prompt engineering, but I think this is the best way of summarising the form into something easily consumable


Prototype logic
---------------

### Team/opposition strength:

**Points per game (PPG = points / matches played) is used to define strength of team** (opposition strength, point 2 in Context).

All data can be derived from home/away variants of Table.

**Each team’s home and away PPG is ranked in a table of 40** (using 20-team PL as example), so a team like Sunderland may be a 5 at home where they get great results, and a 2 away, where they struggle.

**Shaped percentiles** are used to place each into a 5-tier scale — a good alternative would be z-score. Initially I tested equal percentiles but found we had too many oppositions rated 5 or 1, where these buckets should be exceptional:

*   5 = hardest opposition, top 10%

*   4 = 65–90%

*   3 = 35–65%

*   2 = 10–35%

*   1 = easiest opposition, bottom 10%


**Extra notes:**

Team strength is absolute, not relative: Whether Man City (good) or Tottenham (not good) are facing Brighton (home), Brighton’s strength remains the same.

Issue to handle: teams in different primary competitions, such as FA Cup match btwn Premier League and Championship teams. This could default to lower division = 1, or we only use for domestic league competitions.

Steps:
------

### **1\. Generate synthetic match and season data**

JSON is generated per team.

*   form.entity contains primary team information such as name

*   form.upcoming_event contains info on the next match, which the form widget will be relevant to

*   form.season_context shows high-level performance of team so far across whole season. This is all derived from table, where PPG = points per game (points/matches played).

    *   league_ppg_ holds calculation data for opposition_strength

*   form.form_window shows high-level rollup view of performance of team across form window.

    *   It provides rollups of key data like win/draw/loss record, goals scored and xG as this means the LLM will not have to calculate itself when writing analysis. I think this is important to keep LLM focused on primary task.

    *   opponent_strength_counts is a rollup of how many teams of each strength the team played in their form window

*   form.recent_matches contains details of matches in the form window, including key info, opposition_stength_tier, stats (xG, shots, SoT, red cards, goals minus xG)


### 2\. Narrative summary: qualitative layer of analysis

This stage is optional and could be an iteration: Sometimes stats don’t tell the whole story. Maybe a team had all their players out injured or a referee made terrible decisions which affected the result.

The idea is to use LLM with web search capability to fetch a few match reports about the game and write narrative_summary which logs a qualitative, non-statistical view of the match

### 3\. Statistical assessment: quantitative layer of analysis

Purpose:

*   Decide whether each result was deserved, lucky, unlucky, fair, etc.

*   Keep stats as the primary signal

*   Use narrative as a sense check


Use an LLM call to add statistical_assessment , which labels the match and provides evidence. This will make it easy for later LLM calls to have a clear understanding of the match, without needing to analyse each match individually. It can quickly see the label and choose data which supports any analysis. Labels could also be used on client for user.

```text
"statistical_assessment": {
  "label": "unfair draw",
  "confidence": "high",
  "primary_evidence": [
    "xG for 0.2 vs xG against 1.31 indicating Merseyside Red were more threatening",
    "Merseyside Red had 19 shots and 6 on target compared to North London Red's 5 and 2 shots respectively"
  ],
  "narrative_alignment": "supports"
}
```

### 4\. Final summary generation

form.form_window.summaries contains three summaries: home form, away form and combined form.

```text
"summary": {
  "home_text": "North London Red's home form (last five home matches) reads 3W-2D-0L, with 9 scored and 3 conceded. In chance quality they generated 7.87 xG and allowed 4.74 xG, overperforming xG and conceding fewer than xG.",
  "away_text": "North London Red's away form (last five away matches) reads 2W-2D-1L, with 7 scored and 5 conceded. In chance quality they generated 3.81 xG and allowed 7.31 xG, overperforming xG and conceding fewer than xG.",
  "combined_recent_5_text": "North London Red's last five matches (home+away) reads 2W-3D-0L, with 8 scored and 5 conceded. In chance quality they generated 7.09 xG and allowed 5.51 xG, finishing near xG and conceding near xG."
}
```
