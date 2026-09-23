/* cause.c - THE CAUSE LAW, REVISION 2.
 *          GENERATED; every lane authored by search.
 *
 * Which candidate line to examine first.  Decided for ONE line, from eight
 * measured facts and nothing else.
 *
 *   cause(x) -> 0..15   higher = examine first   0 = cannot be the cause
 *
 * ================== WHAT THE HELD-OUT REAL BUGS SAID ==================
 *
 * Revision 1 was judged on 26 real click fixes.  In the 8 where the guilty
 * line was a candidate at all, EVERY guilty line carried the same word:
 * EF_ALL alone, rank 2.  Real fixes fail an assertion, so no traceback
 * frame; the code is old, so no recency; it is shared, so passing tests run
 * it too.  One weak SPECTRUM lane is all the evidence there is.
 *
 * What outranked them, 36 of the 46 times a line ranked above a guilty one,
 * was one shape: IMPORT + LITERAL at rank 3 - an import-time line that
 * happens to contain a name the assertion mentions.  Six more times it was
 * IMPORT + RECENT.
 *
 * THE PRINCIPLE: AN UNMEASURED LANE IS SILENT, NOT WEAK.  IMPORT says the
 * spectrum COULD NOT LOOK.  It says nothing about guilt.  Revision 1 let it
 * count as a weak SPECTRUM grade, so a lane that saw nothing behaved like
 * evidence, and with any other weak bit it outranked the real line.
 *
 * ONE CELL CHANGED.  SPEC_W was EF_ALL | IMPORT; it is now EF_ALL.  SPEC_S,
 * the other three lanes, the rank and R0 are untouched - IMPORT still
 * EXEMPTS a line from the veto, it just no longer grades it.  16 of the 144
 * reachable words move; all 16 have IMPORT set and EF_ALL clear; every other
 * cell stands.  An IMPORT-only line is rank 1; IMPORT+LITERAL is rank 2, the
 * same as a bare EF_ALL line, and Ochiai breaks the tie - which an import
 * line loses, because its score is 0.
 *
 * Replayed on the logged bits, held out: 3 better, 0 worse, 5 unchanged.
 * 0551bf5358 11.5 -> 4.5, ac6a2acfdb 29.5 -> 3.5, e003331551 11.5 -> 2.5.
 * Top-1 is unchanged; the gain is in the top-5 band, where a human reads.
 *
 *   bit 0 EF_ALL   every failing test executes it          (ef == F)
 *   bit 1 EP_NONE  at least one failing, no passing test   (ef>=1, ep==0)
 *   bit 2 IMPORT   runs only at import time - the spectrum cannot look
 *   bit 3 BISECT   bisect converged and blame says the first bad commit
 *                  last touched this line
 *   bit 4 DIVERGE  first line where the failing run parts from a passing one
 *   bit 5 FRAME    a non-test frame of the failing traceback names it
 *   bit 6 LITERAL  a literal from the failing assertion occurs on it
 *   bit 7 RECENT   changed within the last N commits
 *
 * NO NUMBER HERE IS A WEIGHT.  The four lanes are COUNTED, not weighted:
 * s strong and w weak, and the priority is the dense lexicographic rank of
 * (s, w).  One strong beats any number of weak because the rank says so.
 *
 *   TIME      strong BISECT            weak RECENT
 *   SPECTRUM  strong EF_ALL+EP_NONE    weak EF_ALL
 *   WHY       strong DIVERGE           -
 *   SYMPTOM   strong FRAME+LITERAL     weak FRAME or LITERAL
 *
 * THE VETO IS NOW ITS OWN LANE.  In revision 1, KEEP and SPEC_W were the
 * same expression - EF_ALL|IMPORT - and the law exploited that.  Separating
 * them is the whole change, so KEEP is computed on its own here.  It reads
 * bits 0 and 2, TWO APART, which is why this file is cut to single bits from
 * the start: no carry window spans that gap, and posing KEEP whole ground
 * the search out when the omission law tried it.
 *
 * RANK 5 IS STILL UNREACHABLE: (s=0,w=4) needs all four lanes weak, but WHY
 * has no weak grade, so a non-silent WHY forces s >= 1.  Rank 1 IS now
 * produced - it is exactly the IMPORT-only line, kept but counting nothing.
 *
 * Unreachable words - IMPORT with any of EF_ALL, EP_NONE, DIVERGE - were
 * never posed; the check below confirms the law still lands in 0..15.
 *
 * Judged next on the rich real fixes, never used here, and on click again
 * once the omission regime is measured beside it.  If rich disagrees, the
 * table changes by a stated principle and this file gets a revision 3.
 */
#include <stdio.h>
#include <stdint.h>

static inline int32_t L_EF_ALL  (int32_t x) { return (x & 1); }
static inline int32_t L_EP_NONE (int32_t x) { return (1 & (x >> 1)); }
static inline int32_t L_IMPORT  (int32_t x) { return (1 & (x >> 2)); }
static inline int32_t L_BISECT  (int32_t x) { return (1 & (x >> 3)); }
static inline int32_t L_DIVERGE (int32_t x) { return (1 & (x >> 4)); }
static inline int32_t L_FRAME   (int32_t x) { return (1 & (x >> 5)); }
static inline int32_t L_LITERAL (int32_t x) { return (1 & (x >> 6)); }
static inline int32_t L_RECENT  (int32_t x) { return (x >> 7); }
static inline int32_t L_F      (int32_t x) { return ((x + (x - (x >> 1))) + (x + (x & (4 - x)))); }

static inline int32_t KEEP  (int32_t x)   /* R0: IMPORT exempts, never grades */
{ return L_EF_ALL(x) | L_IMPORT(x); }
static inline int32_t STRONG(int32_t x)
{ return (L_EF_ALL(x) & L_EP_NONE(x)) + L_BISECT(x) + L_DIVERGE(x)
       + (L_FRAME(x) & L_LITERAL(x)); }
static inline int32_t NONSIL(int32_t x)   /* SPECTRUM is non-silent on EF_ALL */
{ return L_EF_ALL(x) + (L_BISECT(x) | L_RECENT(x)) + L_DIVERGE(x)
       + (L_FRAME(x) | L_LITERAL(x)); }

int32_t cause(int32_t x)
{ return ((0 - KEEP(x)) & (1 + NONSIL(x) + L_F(STRONG(x)))) & 15; }

/* ===== INDEPENDENT ORACLE: branchy, shares no expression with a lane ==== */
static const int BASE[5] = {0, 5, 9, 12, 14};
static int oracle(int x)
{   int ef=(x>>0)&1, ep=(x>>1)&1, im=(x>>2)&1, bi=(x>>3)&1;
    int dv=(x>>4)&1, fr=(x>>5)&1, li=(x>>6)&1, re=(x>>7)&1;
    int t, sp, wy, sy, s = 0, w = 0;
    if (!ef && !im) return 0;
    if (bi) t = 2; else if (re) t = 1; else t = 0;
    if (ef && ep) sp = 2; else if (ef) sp = 1; else sp = 0;   /* REVISION 2 */
    if (dv) wy = 2; else wy = 0;
    if (fr && li) sy = 2; else if (fr || li) sy = 1; else sy = 0;
    if (t==2) s++;  else if (t==1) w++;
    if (sp==2) s++; else if (sp==1) w++;
    if (wy==2) s++; else if (wy==1) w++;
    if (sy==2) s++; else if (sy==1) w++;
    return 1 + BASE[s] + w; }
static int oracle_v1(int x)   /* revision 1, to report exactly what moved */
{   int ef=(x>>0)&1, ep=(x>>1)&1, im=(x>>2)&1, bi=(x>>3)&1;
    int dv=(x>>4)&1, fr=(x>>5)&1, li=(x>>6)&1, re=(x>>7)&1;
    int t, sp, wy, sy, s = 0, w = 0;
    if (!ef && !im) return 0;
    if (bi) t = 2; else if (re) t = 1; else t = 0;
    if (ef && ep) sp = 2; else if (ef || im) sp = 1; else sp = 0;
    if (dv) wy = 2; else wy = 0;
    if (fr && li) sy = 2; else if (fr || li) sy = 1; else sy = 0;
    if (t==2) s++;  else if (t==1) w++;
    if (sp==2) s++; else if (sp==1) w++;
    if (wy==2) s++; else if (wy==1) w++;
    if (sy==2) s++; else if (sy==1) w++;
    return 1 + BASE[s] + w; }
static int reach(int x)
{ return !(((x>>2)&1) && (((x>>0)&1)||((x>>1)&1)||((x>>4)&1))); }
static int s_of(int x){
    return (((x>>0)&1)&&((x>>1)&1)) + ((x>>3)&1) + ((x>>4)&1)
         + (((x>>5)&1)&&((x>>6)&1)); }
static int w_of(int x){
    int ef=(x>>0)&1,ep=(x>>1)&1,bi=(x>>3)&1,fr=(x>>5)&1,li=(x>>6)&1,re=(x>>7)&1;
    return (!bi&&re) + (ef&&!ep) + (!(fr&&li)&&(fr||li)); }

int main(void)
{
    long tab=0,r0=0,r1=0,r2=0,r3=0,rng=0,anc=0,nre=0,moved=0,imp=0;
    int x,y,i;
    for (x=0;x<256;x++) if (reach(x)) { nre++;
        if (cause(x)!=oracle(x)) tab++;
        if (oracle(x)!=oracle_v1(x)) { moved++;
            if (!(((x>>2)&1) && !((x>>0)&1))) imp++; } }
    printf("  reachable words                            %ld  (want 144)\n", nre);
    printf("  against the revised table, all 144         %ld\n", tab);
    printf("  words whose rank moved from revision 1     %ld  (want 16)\n", moved);
    printf("  moved words NOT (IMPORT set, EF_ALL clear) %ld\n", imp);
    for (x=0;x<256;x++) if (reach(x))
        if (!((x>>0)&1) && !((x>>2)&1) && cause(x)!=0) r0++;
    printf("  R0 no EF_ALL and no IMPORT -> 0            %ld\n", r0);
    for (x=0;x<256;x++) if (reach(x) && cause(x))
      for (y=0;y<256;y++) if (reach(y) && cause(y)) {
        int sx=s_of(x), wx=w_of(x), sy2=s_of(y), wy2=w_of(y);
        if (sx>sy2 && !(cause(x)>cause(y))) r1++;
        if (sx==sy2 && wx>wy2 && !(cause(x)>cause(y))) r1++;
        if (sx==sy2 && wx==wy2 && cause(x)!=cause(y)) r3++; }
    printf("  R1 one strong beats any number of weak     %ld\n", r1);
    printf("  R3 only the counts matter, no lane wins    %ld\n", r3);
    for (x=0;x<256;x++) if (reach(x))
        for (i=0;i<8;i++) { if (i==2) continue;
            if (!(x&(1<<i)) && reach(x|(1<<i))
                && cause(x|(1<<i)) < cause(x)) r2++; }
    printf("  R2 monotone, IMPORT excepted               %ld\n", r2);
    {   long impm=0;
        for (x=0;x<256;x++) if (reach(x) && !((x>>2)&1) && reach(x|4))
            if (cause(x|4) < cause(x)) impm++;
        printf("  and IMPORT now lowers nothing either       %ld"
               "   <- it adds nothing, so it cannot\n", impm);
        r2 += impm; }
    for (x=0;x<256;x++) { int a=cause(x); if (a<0||a>15) rng++; }
    printf("  total on 0..255, lands in 0..15            %ld\n", rng);
    {   const int AX[5]={11,12,1,34,68}, AW[5]={10,6,2,0,2};
        const char *AN[5]={
          "EF_ALL+EP_NONE+BISECT   rich segment.py",
          "IMPORT+BISECT           module constant (was 7)",
          "EF_ALL                  a shared helper",
          "FRAME+EP_NONE           frame, not EF_ALL",
          "IMPORT+LITERAL          import naming Command (was 3)"};
        printf("\n  THE ANCHORS\n");
        for (i=0;i<5;i++) { int a=cause(AX[i]);
            if (a!=AW[i]) anc++;
            printf("    x=%-3d %-44s -> %2d  (want %2d)\n",
                   AX[i], AN[i], a, AW[i]); }
        printf("    x=4   %-44s -> %2d  (want  1)\n",
               "IMPORT alone            kept, counts nothing", cause(4));
        if (cause(4)!=1) anc++; }
    printf("\n  TOTAL  %ld violations\n",
           tab+r0+r1+r2+r3+rng+anc+(nre!=144)+(moved!=16)+imp);
    return (tab+r0+r1+r2+r3+rng+anc+(nre!=144)+(moved!=16)+imp) != 0;
}
