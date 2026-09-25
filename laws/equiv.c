/* equiv.c - THE EQUIV LAW.  GENERATED; every lane authored by search.
 *
 * Two different programs both pass the whole suite.  What to do with the
 * oracle's answer about them.  Decided for ONE ambiguous pair, from eight
 * measured facts and nothing else.
 *
 *   equiv(x) -> 0 REFUSE   ship nothing; the pair stays ambiguous
 *               1 SHIP_A
 *               2 SHIP_B
 *               3 ASK      ask again - a deciding test, or a covering probe
 *
 * ================== THE ORACLE SUPPLIES DATA, NEVER A CHOICE ==============
 *
 * The AI agent is used as an ORACLE: it hands over one fact - a test, or a
 * NO-DIFFERENCE claim with a probe - and the law rules on WHAT WAS MEASURED
 * OF IT, never on what it said.  Measured live on click the same day: at
 * core.py:1877 its test passed under `and` and failed under
 * `self.context_settings`, and the pair shipped - right.  At
 * _termui_impl.py:579 it answered, correctly, that the two spellings of the
 * LESS lookup behave the same, and the body REFUSED, because nothing in it
 * could weigh an equivalence claim.  Every branch it had was a guess: what
 * if the test passes both?  fails both?  flips on a re-run?  what if the
 * probe never reaches the lines that differ?
 *
 *   bit 0   SAME_AST   A and B parse to the same tree
 *   bit 1-2 KIND       0 no usable answer, 1 a test, 2 NO-DIFFERENCE+probe
 *   bit 3   E1         KIND=1: the test passes under A
 *                      KIND=2: the probe executed EVERY differing line
 *   bit 4   E2         KIND=1: the test passes under B
 *                      KIND=2: the outputs were byte-identical
 *   bit 5   SMALLER_A  A's edit changes no more characters than B's
 *   bit 6   LAST_ASK   the ask budget is spent
 *   bit 7   STABLE     the re-run agreed with the first run
 *
 * ============================ THE FOUR REGIMES ============================
 *
 * SAME_AST and the two-bit KIND field select four disjoint regimes that
 * cover the 70 reachable words exactly, and each is the spec's own rule:
 *
 *   Q0  SAME_AST     one program written twice: ship the smaller edit.
 *                    Nothing else is consulted.
 *   Q1  KIND = 0     no answer is no evidence: ASK, or REFUSE if spent.
 *   Q2  KIND = 1     a test decides only what it was SEEN to separate.
 *   Q3  KIND = 2     an equivalence claim ships only on measured evidence:
 *                    stable, covering, and identical - all three or none.
 *
 *   SM  = 2 - SMALLER_A         ship the smaller edit: 1 = A, 2 = B
 *   ASK = 3 - 3*LAST_ASK        ask unless the budget is spent
 *   T1  = (E1 + 2*E2), zeroed when E1 & E2 & LAST_ASK
 *   G2  = STABLE & E1 & E2      the probe's evidence, all three or nothing
 *
 * T1 IS THE ONE WORTH READING.  With a stable test in hand, E1 + 2*E2 IS
 * the verdict already: 0 both fail so REFUSE, 1 only A passes so SHIP_A,
 * 2 only B passes so SHIP_B, 3 both pass - which separates nothing, and 3
 * is ASK.  The four cases of Q2 are not selected between; they are the
 * arithmetic of two bits.  The only correction is that 3 must fall to 0
 * when the budget is spent, since ASK is then REFUSE.
 *
 * Q2's fourth case is the one that never asks again: a stable test that
 * BOTH candidates fail is the oracle's own statement of the intended
 * behaviour met by neither program, and no further answer can make either
 * right.  T1 gives 0 there whatever LAST_ASK says, which is the rule.
 *
 * CLAIMS NEVER SHIP (Q5).  Every SHIP is backed by SAME_AST, a stable
 * separating test, or a stable covering identical probe.  No verdict
 * depends on what the oracle SAID beyond which kind of evidence it handed
 * over.  Checked by enumeration below, not argued.
 *
 * 70 of the 256 words are reachable; the rest were never posed and the
 * check below confirms the law still lands in 0..3 on them.
 *
 * What this law does NOT decide: whether a covering probe with identical
 * output is enough evidence of equivalence in practice.  That is measured
 * on known-equivalent and known-different pairs, and if the probe ships a
 * different pair the MEASUREMENT of E1/E2 gets stricter - never the table.
 */
#include <stdio.h>
#include <stdint.h>

static inline int32_t L_SAME (int32_t x) { return (x & 1); }
static inline int32_t L_E1   (int32_t x) { return (1 & (x >> 3)); }
static inline int32_t L_E2   (int32_t x) { return (1 & (x >> 4)); }
static inline int32_t L_SMA  (int32_t x) { return (1 & (x >> 5)); }
static inline int32_t L_LAST (int32_t x) { return (1 & (x >> 6)); }
static inline int32_t L_STB  (int32_t x) { return (x >> 7); }
static inline int32_t L_K0   (int32_t x) { return ((1 | (x >> 2)) - ((x + 3) >> 2)); }
static inline int32_t L_K1   (int32_t x) { return (1 & (x >> 1)); }
static inline int32_t L_K2   (int32_t x) { return (1 & (x >> 2)); }

static inline int32_t SM (int32_t x){ return 2 - L_SMA(x); }
static inline int32_t ASK(int32_t x){ return 3 - 3*L_LAST(x); }
static inline int32_t T1 (int32_t x)
{ return (L_E1(x) + 2*L_E2(x))
       & ~(0 - (L_E1(x) & L_E2(x) & L_LAST(x))); }
static inline int32_t G2 (int32_t x)
{ return L_STB(x) & L_E1(x) & L_E2(x); }

int32_t equiv(int32_t x)
{   int32_t st = 0 - L_STB(x), g2 = 0 - G2(x);
    return ((( 0 - L_SAME(x)) & SM(x))
          | (( 0 - L_K0(x))   & ASK(x))
          | (( 0 - L_K1(x))   & ((st & T1(x)) | (~st & ASK(x))))
          | (( 0 - L_K2(x))   & ((g2 & SM(x)) | (~g2 & ASK(x))))) & 3; }

/* ===== INDEPENDENT ORACLE: branchy, shares no expression with a lane ==== */
static int oracle(int x)
{   int sa=x&1, k=(x>>1)&3, e1=(x>>3)&1, e2=(x>>4)&1;
    int sm=(x>>5)&1, la=(x>>6)&1, st=(x>>7)&1;
    int S = sm ? 1 : 2, A = la ? 0 : 3;
    if (sa) return S;                                    /* Q0 */
    if (k == 0) return A;                                /* Q1 */
    if (k == 1) {                                        /* Q2 */
        if (!st) return A;
        if (e1 && !e2) return 1;
        if (e2 && !e1) return 2;
        if (e1 && e2)  return A;
        return 0; }
    return (st && e1 && e2) ? S : A; }                   /* Q3 */
static int reach(int x)
{   int sa=x&1, k=(x>>1)&3, e1=(x>>3)&1, e2=(x>>4)&1;
    int la=(x>>6)&1, st=(x>>7)&1;
    if (k == 3) return 0;
    if (sa && (k || e1 || e2 || la || st)) return 0;
    if (k == 0 && (e1 || e2 || st)) return 0;
    return 1; }

int main(void)
{
    long tab=0,q0=0,q1=0,q2=0,q3=0,q4=0,q5=0,rng=0,anc=0,nre=0;
    long n[4]={0,0,0,0};
    int x,i;
    for (x=0;x<256;x++) if (reach(x)) { nre++;
        if (equiv(x)!=oracle(x)) tab++;
        n[equiv(x)&3]++; }
    printf("  reachable words                            %ld  (want 70)\n", nre);
    printf("  against the table, all 70 reachable        %ld\n", tab);
    printf("  partition REFUSE %ld ASK %ld SHIP_A %ld SHIP_B %ld"
           "   (want 30/26/7/7)\n", n[0],n[3],n[1],n[2]);
    if (n[0]!=30||n[3]!=26||n[1]!=7||n[2]!=7) tab++;
    /* Q0-Q5 re-enumerated ON THE KERNEL, not read off the table */
    for (x=0;x<256;x++) if (reach(x)) {
        int sa=x&1, k=(x>>1)&3, e1=(x>>3)&1, e2=(x>>4)&1;
        int sm=(x>>5)&1, la=(x>>6)&1, st=(x>>7)&1, v=equiv(x);
        if (sa && v != (sm?1:2)) q0++;                    /* Q0 */
        if (!sa && k==0 && v != (la?0:3)) q1++;           /* Q1 */
        if (!sa && k==1 && st && !e1 && !e2 && v!=0) q2++;
        if (!sa && k==1 && st && e1 && !e2 && v!=1) q2++;
        if (!sa && k==1 && st && e2 && !e1 && v!=2) q2++;
        if (!sa && k==2 && st && e1 && e2 && v != (sm?1:2)) q3++;
        if (!sa && k==2 && !(st&&e1&&e2) && v != (la?0:3)) q3++;
        if (la && v==3) q4++;                             /* Q4 */
        if ((v==1||v==2) && !(sa || (k==1&&st&&(e1^e2))
                               || (k==2&&st&&e1&&e2))) q5++; }
    printf("  Q0 one program: ship the smaller edit      %ld\n", q0);
    printf("  Q1 no answer is no evidence                %ld\n", q1);
    printf("  Q2 a test decides what it separated        %ld\n", q2);
    printf("  Q3 a claim ships only on measured evidence %ld\n", q3);
    printf("  Q4 the budget is respected: no ASK on LAST %ld\n", q4);
    printf("  Q5 claims never ship: every SHIP is backed %ld\n", q5);
    for (x=0;x<256;x++) { int v=equiv(x); if (v<0||v>3) rng++; }
    printf("  total on 0..255, lands in 0..3             %ld\n", rng);
    {   const int AX[7]={33,138,178,188,148,130,64};
        const int AW[7]={ 1,  1,  2,  1,  3,  0, 0};
        const char *AN[7]={
          "a twin, A the smaller edit",
          "click core.py:1877      test passes A only",
          "click _textwrap.py:168  test passes B only",
          "click _termui_impl:579  probe covers, identical",
          "the probe missed a differing line",
          "a stable test both candidates fail",
          "no usable answer, ask budget spent"};
        const char *VN[4]={"REFUSE","SHIP_A","SHIP_B","ASK"};
        printf("\n  THE ANCHORS\n");
        for (i=0;i<7;i++) { int v=equiv(AX[i]);
            if (v!=AW[i]) anc++;
            printf("    x=%-4d %-42s -> %-6s (want %s)\n",
                   AX[i], AN[i], VN[v], VN[AW[i]]); } }
    printf("\n  TOTAL  %ld violations\n",
           tab+q0+q1+q2+q3+q4+q5+rng+anc+(nre!=70));
    return (tab+q0+q1+q2+q3+q4+q5+rng+anc+(nre!=70)) != 0;
}
