ccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
c      written by the UFO converter
ccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc

      SUBROUTINE COUP3( )

      IMPLICIT NONE

      INCLUDE 'model_functions.inc'

      DOUBLE PRECISION PI, ZERO
      PARAMETER  (PI=3.141592653589793D0)
      PARAMETER  (ZERO=0D0)
      INCLUDE 'input.inc'
      INCLUDE 'coupl.inc'
      GC_4 = -G
      GC_5 = MDL_COMPLEXI*G
      R2_GQQ = -MDL_COMPLEXI*MDL_G__EXP__3/(1.600000D+01*PI**2)
     $ *((MDL_NCOL__EXP__2-1.000000D+00)/(2.000000D+00*MDL_NCOL))
     $ *(1.000000D+00+MDL_LHV)
      R2_QQQ = MDL_LHV*MDL_COMPLEXI*MDL_G__EXP__2*(MDL_NCOL__EXP__2
     $ -1.000000D+00)/(3.200000D+01*PI**2*MDL_NCOL)
      UV_GQQG_1EPS = MDL_COMPLEXI*MDL_G_UVG_1EPS_*G
      UV_GQQB_1EPS = MDL_COMPLEXI*MDL_G_UVB_1EPS_*G
      UVWFCT_G_1_1EPS = COND(DCMPLX(MDL_MB),DCMPLX(0.000000D+00)
     $ ,DCMPLX(-((MDL_G__EXP__2)/(2.000000D+00*4.800000D+01*PI**2))
     $ *4.000000D+00*MDL_TF))
      R2_BXTW = ((MDL_CKM33*MDL_EE*MDL_COMPLEXI)/(MDL_SW*MDL_SQRT__2))
     $ *MDL_R2MIXEDFACTOR_FIN_
      UV_GQQB = MDL_COMPLEXI*MDL_G_UVB_FIN_*G
      UV_GQQT = MDL_COMPLEXI*MDL_G_UVT_FIN_*G
      UVWFCT_G_1 = COND(DCMPLX(MDL_MB),DCMPLX(0.000000D+00)
     $ ,DCMPLX(((MDL_G__EXP__2)/(2.000000D+00*4.800000D+01*PI**2))
     $ *4.000000D+00*MDL_TF*REGLOG(DCMPLX(MDL_MB__EXP__2
     $ /MDL_MU_R__EXP__2))))
      UVWFCT_G_2 = COND(DCMPLX(MDL_MT),DCMPLX(0.000000D+00)
     $ ,DCMPLX(((MDL_G__EXP__2)/(2.000000D+00*4.800000D+01*PI**2))
     $ *4.000000D+00*MDL_TF*REGLOG(DCMPLX(MDL_MT__EXP__2
     $ /MDL_MU_R__EXP__2))))
      END
