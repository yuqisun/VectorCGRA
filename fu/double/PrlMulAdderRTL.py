"""
==========================================================================
PrlMulAdderRTL.py
==========================================================================
Mul and Adder in parallel for CGRA tile.

Author : Cheng Tan
  Date : November 28, 2019
"""


from pymtl3 import *
from ..basic.TwoPrlCombo import TwoPrlCombo
from ..single.MulRTL import MulRTL
from ..single.AdderRTL import AdderRTL
from ...lib.basic.val_rdy.ifcs import ValRdyRecvIfcRTL as RecvIfcRTL
from ...lib.basic.val_rdy.ifcs import ValRdySendIfcRTL as SendIfcRTL
from ...lib.opt_type import *

class PrlMulAdderRTL(TwoPrlCombo):

  def construct(s, DataType, PredicateType, CtrlType,
                num_inports, num_outports, data_mem_size):

    super(PrlMulAdderRTL, s).construct(DataType, PredicateType, CtrlType,
                                       MulRTL, AdderRTL, num_inports,
                                       num_outports, data_mem_size)

    FuInType = mk_bits(clog2(num_inports + 1))

    @update
    def update_opt():


      s.Fu0.recv_opt.msg @= s.recv_opt.msg
      s.Fu1.recv_opt.msg @= s.recv_opt.msg
  
      s.Fu0.recv_opt.msg.fu_in[0] @= 1
      s.Fu0.recv_opt.msg.fu_in[1] @= 2
      s.Fu1.recv_opt.msg.fu_in[0] @= 1
      s.Fu1.recv_opt.msg.fu_in[1] @= 2

      # Note that the predication for a combined FU should be identical/shareable,
      # which means the computation in different basic block cannot be combined.
      s.Fu0.recv_opt.msg.predicate @= s.recv_opt.msg.predicate
      s.Fu1.recv_opt.msg.predicate @= s.recv_opt.msg.predicate

      if s.recv_opt.msg.operation == OPT_MUL_ADD:
        s.Fu0.recv_opt.msg.operation @= OPT_MUL
        s.Fu1.recv_opt.msg.operation @= OPT_ADD
      elif s.recv_opt.msg.operation == OPT_MUL_SUB:
        s.Fu0.recv_opt.msg.operation @= OPT_MUL
        s.Fu1.recv_opt.msg.operation @= OPT_SUB
      else:
        # Indicates no computation should happen no this fused FU.
        s.Fu0.recv_opt.msg.operation @= OPT_START
        s.Fu1.recv_opt.msg.operation @= OPT_START

      # TODO: can handle the customized cases if there are.

