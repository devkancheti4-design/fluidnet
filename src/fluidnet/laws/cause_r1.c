/* cause.c - THE CAUSE LAW.  GENERATED; every lane authored by search.
 *
 * Which candidate line to examine first.  Decided for ONE line, from eight
 * measured facts and nothing else.
 *
 *   cause(x) -> 0..15   higher = examine first   0 = cannot be the cause
 *
 * THE BODY MEASURES, THE LAW RULES.  The body's whole job is to turn what is
 * known about a line into one byte:
 *
 *   bit 0 EF_ALL   every failing test executes it          (ef == F)
 *   bit 1 EP_NONE  at least one failing, no passing test   (ef>=1, ep==0)
 *   bit 2 IMPORT   runs only at import time - coverage but no test context,
 *                  so the spectrum cannot see it
 *   bit 3 BISECT   bisect converged and blame says the first bad commit
 *                  last touched this line
 *   bit 4 DIVERGE  first line where the failing run departs from a passing one
 *   bit 5 FRAME    a non-test frame of the failing traceback names it
 *   bit 6 LITERAL  a literal from the failing assertion occurs on it
 *   bit 7 RECENT   changed within the last N commits of its file
 *
 * No number in this file is a weight.  The body used to add 3 for a frame and
 * 2 for the introducing commit and nothing said why, and the sum let three
 * weak signals outvote one decisive one.  Here the four evidence lanes are
 * counted, not weighted: s lanes STRONG and w lanes WEAK, and the priority is
 * the dense lexicographic rank of (s, w).  One strong beats any number of
 * weak because the rank says so, not because a constant was chosen.
 *
 * THE CUT, and it took three passes to find.  Posed whole the search ground
 * out; the regime lines are:
 *   1  the four lanes are independent, so four lanes, not one expression;
 *   2  a grade lane is itself two lanes - TIME reads bit 3 and bit 7, FOUR
 *      APART, and no carry window spans that gap.  Written S for strong and
 *      W for non-silent, every lane is grade = S + W, so eight booleans;
 *   3  the rank is 1 + N + (BASE[s] - s), where N enters LINEARLY and s
 *      QUADRATICALLY.  N needs no lane at all; the whole nonlinearity is one
 *      five-value lane F(s) = 0, 4, 7, 9, 10.
 *
 * R0 IS NOT A SEPARATE RULE.  SPEC_W is EF_ALL | IMPORT, which is exactly the
 * reachability veto's condition: the veto fires precisely when the SPECTRUM
 * lane is silent.  The mask below is that same lane negated, so the rule and
 * the measurement are one thing rather than two.
 *
 * WHY cause 5 NEVER APPEARS.  (s=0, N=4) is unreachable: WHY is strong
 * whenever it is non-silent - it has no weak grade - so any N that counts WHY
 * forces s >= 1.  Fourteen sums are reachable, not fifteen.
 *
 * Unreachable words - IMPORT with any of EF_ALL, EP_NONE, DIVERGE - were
 * never posed; the law may do anything there and the check below confirms it
 * still lands in 0..15.
 *
 * What this law does NOT decide: whether the ranking finds real bugs.  That
 * is measured on real fixes, held out, and if it says the table is wrong the
 * table changes by a stated principle and a new kernel is asked for.
 */
#include <stdio.h>
#include <stdint.h>

static inline int32_t L_SPEC_W (int32_t x) { return ((x & 1) + (1 & (x >> 2))); }
static inline int32_t L_SPEC_S (int32_t x) { return ((0 - (x >> 2)) + ((x + 1) >> 2)); }
static inline int32_t L_TIME_S (int32_t x) { return (1 & (x >> 3)); }
static inline int32_t L_TIME_W (int32_t x) { return ((0 - ((x >> 4) << 1)) + ((x >> 3) | (x >> 7))); }
static inline int32_t L_WHY    (int32_t x) { return (1 & (x >> 4)); }
static inline int32_t L_SYMP_S (int32_t x) { return ((0 - (x >> 7)) + ((x + 32) >> 7)); }
static inline int32_t L_SYMP_W (int32_t x) { return ((1 - (x >> 7)) + ((x - 32) >> 7)); }
static inline int32_t L_F     (int32_t x) { return ((x + (x - (x >> 1))) + (x + (x & (4 - x)))); }

static inline int32_t STRONG(int32_t x)
{ return L_TIME_S(x) + L_SPEC_S(x) + L_WHY(x) + L_SYMP_S(x); }
static inline int32_t NONSIL(int32_t x)
{ return L_TIME_W(x) + L_SPEC_W(x) + L_WHY(x) + L_SYMP_W(x); }

int32_t cause(int32_t x)
{   return ((0 - L_SPEC_W(x)) & (1 + NONSIL(x) + L_F(STRONG(x)))) & 15; }

/* ===== INDEPENDENT ORACLE: branchy, shares no expression with a lane ==== */
static const int BASE[5] = {0, 5, 9, 12, 14};
static int oracle(int x)
{   int ef=(x>>0)&1, ep=(x>>1)&1, im=(x>>2)&1, bi=(x>>3)&1;
    int dv=(x>>4)&1, fr=(x>>5)&1, li=(x>>6)&1, re=(x>>7)&1;
    int t, sp, wy, sy, s = 0, w = 0;
    if (!ef && !im) return 0;                     /* R0 */
    if (bi) t = 2; else if (re) t = 1; else t = 0;
    if (ef && ep) sp = 2; else if (ef || im) sp = 1; else sp = 0;
    if (dv) wy = 2; else wy = 0;
    if (fr && li) sy = 2; else if (fr || li) sy = 1; else sy = 0;
    if (t==2) s++;  else if (t==1) w++;
    if (sp==2) s++; else if (sp==1) w++;
    if (wy==2) s++; else if (wy==1) w++;
    if (sy==2) s++; else if (sy==1) w++;
    return 1 + BASE[s] + w; }
static int reach(int x){ return !(((x>>2)&1) && (((x>>0)&1)||((x>>1)&1)||((x>>4)&1))); }
static int s_of(int x){ int ef=(x>>0)&1,ep=(x>>1)&1,bi=(x>>3)&1,dv=(x>>4)&1;
    int fr=(x>>5)&1,li=(x>>6)&1;
    return bi + (ef&&ep) + dv + (fr&&li); }
static int w_of(int x){ int ef=(x>>0)&1,ep=(x>>1)&1,im=(x>>2)&1,bi=(x>>3)&1;
    int fr=(x>>5)&1,li=(x>>6)&1,re=(x>>7)&1;
    return (!bi&&re) + (!(ef&&ep)&&(ef||im)) + (!(fr&&li)&&(fr||li)); }

int main(void)
{
    long tab=0, r0=0, r1=0, r2=0, r3=0, rng=0, lane=0, anc=0, nre=0;
    int x, y, i;
    for (x=0;x<256;x++) if (reach(x)) { nre++;
        if (cause(x) != oracle(x)) tab++; }
    printf("  reachable words                            %ld  (want 144)\n", nre);
    printf("  against the table, all 144 reachable       %ld\n", tab);
    /* each lane against its own spec, independently */
    for (x=0;x<256;x++) if (reach(x)) {
        int ef=(x>>0)&1, ep=(x>>1)&1, im=(x>>2)&1, bi=(x>>3)&1;
        int dv=(x>>4)&1, fr=(x>>5)&1, li=(x>>6)&1, re=(x>>7)&1;
        if (L_SPEC_W(x) != (ef||im))      lane++;
        if (L_SPEC_S(x) != (ef&&ep))      lane++;
        if (L_TIME_S(x) != bi)            lane++;
        if (L_TIME_W(x) != (bi||re))      lane++;
        if (L_WHY(x)    != dv)            lane++;
        if (L_SYMP_S(x) != (fr&&li))      lane++;
        if (L_SYMP_W(x) != (fr||li))      lane++; }
    printf("  each lane against its own spec             %ld\n", lane);
    for (i=0;i<5;i++) if (L_F(i) != BASE[i]-i) lane++;
    printf("  F(s) == BASE[s] - s over s = 0..4          %ld\n", lane);
    /* R0 by enumeration on the KERNEL, not on the table */
    for (x=0;x<256;x++) if (reach(x))
        if (!((x>>0)&1) && !((x>>2)&1) && cause(x)!=0) r0++;
    printf("  R0 no EF_ALL and no IMPORT -> 0            %ld\n", r0);
    /* R1 dense lexicographic rank, and R3 no lane privileged */
    for (x=0;x<256;x++) if (reach(x) && cause(x))
      for (y=0;y<256;y++) if (reach(y) && cause(y)) {
        int sx=s_of(x), wx=w_of(x), sy2=s_of(y), wy2=w_of(y);
        if (sx>sy2       && !(cause(x)>cause(y)))  r1++;
        if (sx==sy2 && wx>wy2 && !(cause(x)>cause(y))) r1++;
        if (sx==sy2 && wx==wy2 && cause(x)!=cause(y))  r3++; }
    printf("  R1 one strong beats any number of weak    %ld\n", r1);
    printf("  R3 only the counts matter, no lane wins    %ld\n", r3);
    /* R2 monotone in every evidence bit except IMPORT */
    for (x=0;x<256;x++) if (reach(x))
        for (i=0;i<8;i++) { if (i==2) continue;
            if (!(x&(1<<i)) && reach(x|(1<<i))
                && cause(x|(1<<i)) < cause(x)) r2++; }
    printf("  R2 monotone, IMPORT excepted               %ld\n", r2);
    for (x=0;x<256;x++) { int a=cause(x); if (a<0||a>15) rng++; }
    printf("  total on 0..255, lands in 0..15            %ld\n", rng);
    {   const int AX[4]={11,12,1,34}, AW[4]={10,7,2,0};
        const char *AN[4]={"rich segment.py: ef==F, ep==0, bisect",
                           "module constant the bad commit changed",
                           "a shared helper every test runs",
                           "frame on a line only one failing test runs"};
        printf("\n  THE ANCHORS\n");
        for (i=0;i<4;i++) { int a=cause(AX[i]);
            if (a!=AW[i]) anc++;
            printf("    x=%-3d %-42s -> %2d  (want %2d)\n",
                   AX[i], AN[i], a, AW[i]); } }
    printf("\n  TOTAL  %ld violations\n",
           tab+r0+r1+r2+r3+rng+lane+anc+(nre!=144));
    return (tab+r0+r1+r2+r3+rng+lane+anc+(nre!=144)) != 0;
}
