/* omission.c - THE OMISSION LAW.  GENERATED; every lane authored by search.
 *
 * Where missing code belongs.  Decided for ONE candidate line, from eight
 * measured facts and nothing else.
 *
 *   omission(x) -> 0..15   higher = examine first   0 = no reach evidence
 *
 * THE CAUSE LAW RANKS LINES THE FAILING TEST EXECUTED.  It is blind to the
 * bug where the fix ADDS code the old file never ran: no line has EF_ALL,
 * because the line does not exist.  A sixth of real fixes are faults of
 * omission and the other law has nothing to say about any of them.  What can
 * still be measured is not where the bug is but WHERE THE PATH STOPPED
 * LOOKING, and that is what this rules on.
 *
 *   bit 0 ENDED     the failing run's last executed source line is this one
 *   bit 1 NEXT      not executed, and the line just before it was - the
 *                   frontier the path stepped past
 *   bit 2 TARGET    inside the function the assertion calls, or the frame
 *                   that raised
 *   bit 3 HEAD      a site missing code goes: a def/class line, or a branch
 *                   or guard head
 *   bit 4 PASSONLY  run by a passing test and by no failing test - where the
 *                   failing run should have gone.  The spectrum, reversed.
 *   bit 5 RAISED    the failure was an exception, not a false assertion.
 *                   Measured once per failure; the same on every line.
 *   bit 6 DIVERGE   first line where the failing run parts from a passing one
 *   bit 7 RECENT    changed within the last N commits
 *
 * NO NUMBER HERE IS A WEIGHT.  The four lanes are COUNTED, not weighted:
 * s lanes strong, w lanes weak, and the priority is the dense lexicographic
 * rank of (s, w).  One strong beats any number of weak because the rank says
 * so, not because a constant was chosen.
 *
 *   EDGE      strong ENDED          weak NEXT
 *   SCOPE     strong TARGET+HEAD    weak TARGET or HEAD
 *   CONTRAST  strong DIVERGE        weak PASSONLY
 *   TIME      -                     weak RECENT
 *
 * RAISED IS NOT A LANE, IT IS THE REGIME, AND IT IS A SHIFT.  With an
 * exception the rank stands; without one the priority is halved, because a
 * false assertion with no exception is usually a WRONG line - the cause
 * law's regime - not a missing one.  Halving by one is a shift by one, so
 * the regime becomes the shift AMOUNT (1 - RAISED) and the law stays a
 * single branchless form instead of forking into two.
 *
 * R0 NEEDS NO LANE OF ITS OWN.  The veto is "no EDGE bit, no CONTRAST bit
 * and not TARGET", which is exactly EDGE_W | TARGET | CONTRAST_W - lanes the
 * law already computes.  Posing a KEEP lane separately was killed twice by
 * the search before the cut showed it was never a lane.
 *
 * RANK 15 IS UNREACHABLE, and that is structural: TIME has no strong grade,
 * so s <= 3 and the top attainable rank is 14 at (3,1).  The mirror of the
 * cause law's missing 5, from the same cause - a lane that can only ever be
 * weak truncates one end of the dense rank.
 *
 * RUN IT BESIDE THE CAUSE LAW, NEVER BLENDED.  "Which executed line is
 * wrong" and "where does missing code belong" are different questions, and a
 * line can be a good answer to one and a vetoed answer to the other.
 *
 * Unreachable words - ENDED with NEXT, or ENDED with PASSONLY - were never
 * posed; the check below confirms the law still lands in 0..15 on them.
 *
 * What this law does NOT decide: whether it finds real omissions.  That is
 * measured on the held-out half of the 35 pure insertions and 57
 * one-to-several fixes, and if it says the table is wrong the table changes
 * by a stated principle and a new kernel is asked for.
 */
#include <stdio.h>
#include <stdint.h>

static inline int32_t L_ENDED    (int32_t x) { return (x & 1); }
static inline int32_t L_NEXT     (int32_t x) { return (1 & (x >> 1)); }
static inline int32_t L_TARGET   (int32_t x) { return (1 & (x >> 2)); }
static inline int32_t L_HEAD     (int32_t x) { return (1 & (x >> 3)); }
static inline int32_t L_PASSONLY (int32_t x) { return (1 & (x >> 4)); }
static inline int32_t L_RAISED   (int32_t x) { return (1 & (x >> 5)); }
static inline int32_t L_DIVERGE  (int32_t x) { return (1 & (x >> 6)); }
static inline int32_t L_RECENT   (int32_t x) { return (x >> 7); }
static inline int32_t L_F       (int32_t x) { return ((x - (x >> 1)) + (x | (x + x))); }

static inline int32_t EDGE_W (int32_t x){ return L_ENDED(x)   | L_NEXT(x); }
static inline int32_t SCOPE_W(int32_t x){ return L_TARGET(x)  | L_HEAD(x); }
static inline int32_t SCOPE_S(int32_t x){ return L_TARGET(x)  & L_HEAD(x); }
static inline int32_t CONTR_W(int32_t x){ return L_DIVERGE(x) | L_PASSONLY(x); }
static inline int32_t KEEP   (int32_t x)
{ return EDGE_W(x) | L_TARGET(x) | CONTR_W(x); }
static inline int32_t STRONG (int32_t x)
{ return L_ENDED(x) + SCOPE_S(x) + L_DIVERGE(x); }
static inline int32_t NONSIL (int32_t x)
{ return EDGE_W(x) + SCOPE_W(x) + CONTR_W(x) + L_RECENT(x); }

int32_t omission(int32_t x)
{   return ((0 - KEEP(x))
          & ((1 + NONSIL(x) + L_F(STRONG(x))) >> (1 - L_RAISED(x)))) & 15; }

/* ===== INDEPENDENT ORACLE: branchy, shares no expression with a lane ==== */
static const int BASE[5] = {0, 5, 9, 12, 14};
static int oracle(int x)
{   int en=(x>>0)&1, nx=(x>>1)&1, tg=(x>>2)&1, hd=(x>>3)&1;
    int po=(x>>4)&1, rs=(x>>5)&1, dv=(x>>6)&1, rc=(x>>7)&1;
    int e, sc, co, ti, s = 0, w = 0, r;
    if (!en && !nx && !tg && !po && !dv) return 0;            /* R0 */
    if (en) e = 2; else if (nx) e = 1; else e = 0;
    if (tg && hd) sc = 2; else if (tg || hd) sc = 1; else sc = 0;
    if (dv) co = 2; else if (po) co = 1; else co = 0;
    if (rc) ti = 1; else ti = 0;
    if (e==2) s++;  else if (e==1) w++;
    if (sc==2) s++; else if (sc==1) w++;
    if (co==2) s++; else if (co==1) w++;
    if (ti==2) s++; else if (ti==1) w++;
    r = 1 + BASE[s] + w;
    if (rs) return r; else return r >> 1; }
static int reach(int x)
{   int en=(x>>0)&1, nx=(x>>1)&1, po=(x>>4)&1;
    return !((en && nx) || (en && po)); }
static int s_of(int x){ return ((x>>0)&1) + (((x>>2)&1)&&((x>>3)&1)) + ((x>>6)&1); }
static int w_of(int x){
    int en=(x>>0)&1,nx=(x>>1)&1,tg=(x>>2)&1,hd=(x>>3)&1;
    int po=(x>>4)&1,dv=(x>>6)&1,rc=(x>>7)&1;
    return (!en&&nx) + (!(tg&&hd)&&(tg||hd)) + (!dv&&po) + rc; }

int main(void)
{
    long tab=0,r0=0,r1=0,r2=0,r3=0,rng=0,anc=0,nre=0,rsm=0;
    int x,y,i;
    for (x=0;x<256;x++) if (reach(x)) { nre++;
        if (omission(x)!=oracle(x)) tab++; }
    printf("  reachable words                            %ld  (want 160)\n", nre);
    printf("  against the table, all 160 reachable       %ld\n", tab);
    for (x=0;x<256;x++) if (reach(x))
        if (!((x>>0)&1) && !((x>>1)&1) && !((x>>2)&1)
            && !((x>>4)&1) && !((x>>6)&1) && omission(x)!=0) r0++;
    printf("  R0 no edge, no contrast, not target -> 0   %ld\n", r0);
    /* R1 and R3 hold WITHIN a regime: RAISED scales the whole ruling, so
       comparing across it is not what the rank governs. */
    for (x=0;x<256;x++) if (reach(x) && omission(x))
      for (y=0;y<256;y++) if (reach(y) && omission(y)
                             && (((x>>5)&1)==((y>>5)&1))) {
        int sx=s_of(x), wx=w_of(x), sy2=s_of(y), wy2=w_of(y);
        if (sx>sy2 && !(omission(x)>=omission(y))) r1++;
        if (sx==sy2 && wx>wy2 && !(omission(x)>=omission(y))) r1++;
        if (sx==sy2 && wx==wy2 && omission(x)!=omission(y)) r3++; }
    printf("  R1 one strong beats any number of weak     %ld\n", r1);
    printf("  R3 only the counts matter, no lane wins    %ld\n", r3);
    for (x=0;x<256;x++) if (reach(x))
        for (i=0;i<8;i++) { if (i==5) continue;
            if (!(x&(1<<i)) && reach(x|(1<<i))
                && omission(x|(1<<i)) < omission(x)) r2++; }
    printf("  R2 monotone, RAISED excepted               %ld\n", r2);
    for (x=0;x<256;x++) if (reach(x) && !((x>>5)&1))
        if (omission(x|32) < omission(x)) rsm++;
    printf("  and monotone in RAISED too, unasked        %ld\n", rsm);
    for (x=0;x<256;x++) { int a=omission(x); if (a<0||a>15) rng++; }
    printf("  total on 0..255, lands in 0..15            %ld\n", rng);
    {   const int AX[5]={45,44,26,128,1}, AW[5]={10,6,2,0,3};
        const char *AN[5]={
          "ENDED+TARGET+HEAD+RAISED  click bec59289d8",
          "TARGET+HEAD+RAISED       click f58ca3e814",
          "NEXT+HEAD+PASSONLY       rich 720800e6",
          "RECENT only              nothing points at it",
          "ENDED alone, RAISED=0    ran to a return"};
        printf("\n  THE ANCHORS\n");
        for (i=0;i<5;i++) { int a=omission(AX[i]);
            if (a!=AW[i]) anc++;
            printf("    x=%-3d %-44s -> %2d  (want %2d)\n",
                   AX[i], AN[i], a, AW[i]); } }
    printf("\n  TOTAL  %ld violations\n",
           tab+r0+r1+r2+r3+rng+anc+(nre!=160));
    return (tab+r0+r1+r2+r3+rng+anc+(nre!=160)) != 0;
}
