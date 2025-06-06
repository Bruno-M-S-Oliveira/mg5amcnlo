      SUBROUTINE SB_SF_003(P,ANS_SUMMED)
C     
C     Generated by MadGraph5_aMC@NLO v. %(version)s, %(date)s
C     By the MadGraph5_aMC@NLO Development Team
C     Visit launchpad.net/madgraph5 and amcatnlo.web.cern.ch
C     
C     
C     Return the sum of the split orders which are required in
C      orders.inc (BORN_ORDERS)
C     Also the values needed for the counterterms are stored in the
C      C_BORN_CNT common block
C     
C     
C     Process: s s~ > t t~ [ LOonly = QCD QED ] QCD^2=6 QED^2=0
C     spectators: 1 4 

C     
C     
C     CONSTANTS
C     
      IMPLICIT NONE
      INCLUDE 'nexternal.inc'
      INTEGER NSQAMPSO
      PARAMETER (NSQAMPSO=1)
C     
C     ARGUMENTS 
C     
      REAL*8 P(0:3,NEXTERNAL), ANS_SUMMED
C     
C     VARIABLES
C     
      INTEGER I,J
      INCLUDE 'orders.inc'
      REAL*8 ANS(0:NSQAMPSO)
      LOGICAL KEEP_ORDER_CNT(NSPLITORDERS, NSQAMPSO)
      COMMON /C_KEEP_ORDER_CNT/ KEEP_ORDER_CNT
      INTEGER AMP_ORDERS(NSPLITORDERS)
      DOUBLE PRECISION TINY
      PARAMETER (TINY = 1D-12)
      DOUBLE PRECISION MAX_VAL
C     
C     FUNCTIONS
C     
      INTEGER GETORDPOWFROMINDEX_B
      INTEGER ORDERS_TO_AMP_SPLIT_POS
C     
C     BEGIN CODE
C     
      CALL SB_SF_003_SPLITORDERS(P,ANS)
C     color-linked borns are called for QCD-type emissions
      ANS_SUMMED = 0D0
      MAX_VAL = 0D0

C     reset the amp_split_cnt array
      AMP_SPLIT_CNT(1:AMP_SPLIT_SIZE,1:2,1:NSPLITORDERS) = DCMPLX(0D0
     $ ,0D0)


      DO I = 1, NSQAMPSO
        MAX_VAL = MAX(MAX_VAL, ABS(ANS(I)))
      ENDDO

      DO I = 1, NSQAMPSO
        IF (KEEP_ORDER_CNT(QCD_POS, I)) THEN
          ANS_SUMMED = ANS_SUMMED + ANS(I)
          DO J = 1, NSPLITORDERS
            AMP_ORDERS(J) = GETORDPOWFROMINDEX_B(J, I)
C           take into account the fact that this is for QCD
            IF (J.EQ.QCD_POS) AMP_ORDERS(J) = AMP_ORDERS(J) + 2
          ENDDO
C         amp_split_cnt(orders_to_amp_split_pos(amp_orders),1,qcd_pos)
C          = ans(I)
          IF(ABS(ANS(I)).GT.MAX_VAL*TINY)
     $      AMP_SPLIT_CNT(ORDERS_TO_AMP_SPLIT_POS(AMP_ORDERS),1
     $     ,QCD_POS) = ANS(I)
        ENDIF
      ENDDO

C     this is to avoid fake non-zero contributions 
      IF (ABS(ANS_SUMMED).LT.MAX_VAL*TINY) ANS_SUMMED=0D0

      RETURN
      END


      SUBROUTINE SB_SF_003_SPLITORDERS(P1,ANS)
C     
C     Generated by MadGraph5_aMC@NLO v. %(version)s, %(date)s
C     By the MadGraph5_aMC@NLO Development Team
C     Visit launchpad.net/madgraph5 and amcatnlo.web.cern.ch
C     
C     RETURNS AMPLITUDE SQUARED SUMMED/AVG OVER COLORS
C     AND HELICITIES
C     FOR THE POINT IN PHASE SPACE P(0:3,NEXTERNAL-1)
C     
C     Process: s s~ > t t~ [ LOonly = QCD QED ] QCD^2=6 QED^2=0
C     spectators: 1 4 

C     
      IMPLICIT NONE
C     
C     CONSTANTS
C     
      INCLUDE 'nexternal.inc'
      INTEGER     NCOMB
      PARAMETER ( NCOMB=  16 )
      INTEGER NSQAMPSO
      PARAMETER (NSQAMPSO=1)
      INTEGER    THEL
      PARAMETER (THEL=NCOMB*0)
      INTEGER NGRAPHS
      PARAMETER (NGRAPHS=   1)
C     
C     ARGUMENTS 
C     
      REAL*8 P1(0:3,NEXTERNAL-1),ANS(0:NSQAMPSO)
C     
C     LOCAL VARIABLES 
C     
      INTEGER IHEL,IDEN,I,J
      DOUBLE PRECISION T(NSQAMPSO)
      INTEGER IDEN_VALUES(1)
      DATA IDEN_VALUES / 36 /
C     
C     GLOBAL VARIABLES
C     
      LOGICAL GOODHEL(NCOMB,0)
      COMMON /C_GOODHEL/ GOODHEL
      DOUBLE PRECISION SAVEMOM(NEXTERNAL-1,2)
      COMMON/TO_SAVEMOM/SAVEMOM
      LOGICAL CALCULATEDBORN
      COMMON/CCALCULATEDBORN/CALCULATEDBORN
      INTEGER NFKSPROCESS
      COMMON/C_NFKSPROCESS/NFKSPROCESS
C     ----------
C     BEGIN CODE
C     ----------
      IDEN=IDEN_VALUES(NFKSPROCESS)
      IF (CALCULATEDBORN) THEN
        DO J=1,NEXTERNAL-1
          IF (SAVEMOM(J,1).NE.P1(0,J) .OR. SAVEMOM(J,2).NE.P1(3,J))
     $      THEN
            CALCULATEDBORN=.FALSE.
            WRITE(*,*) 'Error in sb_sf: momenta not the same in the'
     $       //' born'
            STOP
          ENDIF
        ENDDO
      ELSE
        WRITE(*,*) 'Error in sb_sf: color_linked borns should be'
     $   //' called only with calculatedborn = true'
        STOP
      ENDIF
      DO I=0,NSQAMPSO
        ANS(I) = 0D0
      ENDDO
      DO IHEL=1,NCOMB
        IF (GOODHEL(IHEL,NFKSPROCESS)) THEN
          CALL B_SF_003(IHEL,T)
          DO I=1,NSQAMPSO
            ANS(I)=ANS(I)+T(I)
          ENDDO
        ENDIF
      ENDDO
      DO I=1,NSQAMPSO
        ANS(I)=ANS(I)/DBLE(IDEN)
        ANS(0)=ANS(0)+ANS(I)
      ENDDO
      END


      SUBROUTINE B_SF_003(HELL,ANS)
C     
C     Generated by MadGraph5_aMC@NLO v. %(version)s, %(date)s
C     By the MadGraph5_aMC@NLO Development Team
C     Visit launchpad.net/madgraph5 and amcatnlo.web.cern.ch
C     RETURNS AMPLITUDE SQUARED SUMMED/AVG OVER COLORS
C     FOR THE POINT WITH EXTERNAL LINES W(0:6,NEXTERNAL-1)

C     Process: s s~ > t t~ [ LOonly = QCD QED ] QCD^2=6 QED^2=0
C     spectators: 1 4 

C     
      IMPLICIT NONE
C     
C     CONSTANTS
C     
      INTEGER NAMPSO, NSQAMPSO
      PARAMETER (NAMPSO=1, NSQAMPSO=1)
      INTEGER     NGRAPHS
      PARAMETER ( NGRAPHS = 1 )
      INTEGER NCOLOR1, NCOLOR2
      PARAMETER (NCOLOR1=2, NCOLOR2=2)
      REAL*8     ZERO
      PARAMETER (ZERO=0D0)
      COMPLEX*16 IMAG1
      PARAMETER (IMAG1 = (0D0,1D0))
      INCLUDE 'nexternal.inc'
      INCLUDE 'born_nhel.inc'
C     
C     ARGUMENTS 
C     
      INTEGER HELL
      REAL*8 ANS(NSQAMPSO)
C     
C     LOCAL VARIABLES 
C     
      INTEGER I,J,M,N
      INTEGER CF(NCOLOR2,NCOLOR1),DENOM
      COMPLEX*16 ZTEMP, AMP(NGRAPHS), JAMP1(NCOLOR1,NAMPSO),
     $  JAMP2(NCOLOR2,NAMPSO)
      COMPLEX*16 TMP_JAMP(0)
C     
C     GLOBAL VARIABLES
C     
      DOUBLE COMPLEX SAVEAMP(NGRAPHS,MAX_BHEL)
      COMMON/TO_SAVEAMP/SAVEAMP
      LOGICAL CALCULATEDBORN
      COMMON/CCALCULATEDBORN/CALCULATEDBORN
C     
C     FUNCTION
C     
      INTEGER SQSOINDEXB
C     
C     COLOR DATA
C     
      DATA DENOM/1/
      DATA (CF(I,  1),I=  1,  2) /9,3/
      DATA (CF(I,  2),I=  1,  2) /3,9/
C     ----------
C     BEGIN CODE
C     ----------
      IF (.NOT. CALCULATEDBORN) THEN
        WRITE(*,*) 'Error in b_sf: color_linked borns should be called'
     $   //' only with calculatedborn = true'
        STOP
      ELSEIF (CALCULATEDBORN) THEN
        DO I=1,NGRAPHS
          AMP(I)=SAVEAMP(I,HELL)
        ENDDO
      ENDIF
C     JAMPs contributing to orders QCD=2 QED=0
      JAMP1(1,1) = (1.666666666666667D-01)*AMP(1)
      JAMP1(2,1) = (-5.000000000000000D-01)*AMP(1)
C     JAMPs contributing to orders QCD=2 QED=0
      JAMP2(1,1) = (-2.777777777777778D-01)*AMP(1)
      JAMP2(2,1) = (1.666666666666667D-01)*AMP(1)
      DO I = 1, NSQAMPSO
        ANS(I) = 0D0
      ENDDO
      DO M = 1, NAMPSO
        DO I = 1, NCOLOR1
          ZTEMP = (0.D0,0.D0)
          DO J = 1, NCOLOR2
            ZTEMP = ZTEMP + CF(J,I)*JAMP2(J,M)
          ENDDO
          DO N = 1, NAMPSO
            ANS(SQSOINDEXB(M,N))=ANS(SQSOINDEXB(M,N))+ZTEMP
     $       *DCONJG(JAMP1(I,N))/DENOM
          ENDDO
        ENDDO
      ENDDO
      END



