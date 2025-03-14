'''
=========================================================================
ControllerRTL_test.py
=========================================================================
Simple test for ControllerRTL.

Author : Cheng Tan
  Date : Dec 15, 2024
'''

from pymtl3 import *
from pymtl3.stdlib.test_utils import TestVectorSimulator, config_model_with_cmdline_opts
from ..ControllerRTL import ControllerRTL
from ...lib.basic.val_rdy.SinkRTL import SinkRTL as TestSinkRTL
from ...lib.basic.val_rdy.SourceRTL import SourceRTL as TestSrcRTL
from ...lib.basic.val_rdy.ifcs import ValRdySendIfcRTL as SendIfcRTL
from ...lib.basic.val_rdy.ifcs import ValRdyRecvIfcRTL as RecvIfcRTL
from ...lib.messages import *
from ...lib.cmd_type import *
from ...noc.PyOCN.pymtl3_net.ocnlib.test.stream_sinks import NetSinkRTL as TestNetSinkRTL
import pytest

#-------------------------------------------------------------------------
# TestHarness
#-------------------------------------------------------------------------

class TestHarness(Component):

  def construct(s, ControllerIdType, CtrlPktType, CmdType, MsgType,
                AddrType, PktType, controller_id,
                from_tile_load_request_pkt_msgs,
                from_tile_load_response_pkt_msgs,
                from_tile_store_request_pkt_msgs,
                expected_to_tile_load_request_addr_msgs,
                expected_to_tile_load_response_data_msgs,
                expected_to_tile_store_request_addr_msgs,
                expected_to_tile_store_request_data_msgs,
                from_noc_pkts,
                expected_to_noc_pkts,
                controller2addr_map,
                idTo2d_map, num_terminals):

    cmp_func = lambda a, b : a == b # a.data == b.data

    s.src_from_tile_load_request_pkt_en_rdy = TestSrcRTL(PktType, from_tile_load_request_pkt_msgs)
    s.src_from_tile_load_response_pkt_en_rdy = TestSrcRTL(PktType, from_tile_load_response_pkt_msgs)
    s.src_from_tile_store_request_pkt_en_rdy = TestSrcRTL(PktType, from_tile_store_request_pkt_msgs)

    s.sink_to_tile_load_request_addr_en_rdy = TestSinkRTL(AddrType, expected_to_tile_load_request_addr_msgs)
    s.sink_to_tile_load_response_data_en_rdy = TestSinkRTL(MsgType, expected_to_tile_load_response_data_msgs)
    s.sink_to_tile_store_request_addr_en_rdy = TestSinkRTL(AddrType, expected_to_tile_store_request_addr_msgs)
    s.sink_to_tile_store_request_data_en_rdy = TestSinkRTL(MsgType, expected_to_tile_store_request_data_msgs)

    s.src_from_noc_val_rdy = TestSrcRTL(PktType, from_noc_pkts)
    s.sink_to_noc_val_rdy = TestNetSinkRTL(PktType, expected_to_noc_pkts, cmp_fn = cmp_func)

    s.dut = ControllerRTL(ControllerIdType, CmdType, CtrlPktType,
                          PktType, MsgType, AddrType,
                          # Number of controllers globally (x/y dimension).
                          1, num_terminals,
                          controller_id,
                          controller2addr_map,
                          idTo2d_map)

    # Connections
    s.src_from_tile_load_request_pkt_en_rdy.send //= s.dut.recv_from_tile_load_request_pkt
    s.src_from_tile_load_response_pkt_en_rdy.send //= s.dut.recv_from_tile_load_response_pkt
    s.src_from_tile_store_request_pkt_en_rdy.send //= s.dut.recv_from_tile_store_request_pkt

    s.dut.send_to_tile_load_request_addr //= s.sink_to_tile_load_request_addr_en_rdy.recv
    s.dut.send_to_tile_load_response_data //= s.sink_to_tile_load_response_data_en_rdy.recv
    s.dut.send_to_tile_store_request_addr //= s.sink_to_tile_store_request_addr_en_rdy.recv
    s.dut.send_to_tile_store_request_data //= s.sink_to_tile_store_request_data_en_rdy.recv

    s.src_from_noc_val_rdy.send //= s.dut.recv_from_noc
    s.dut.send_to_noc //= s.sink_to_noc_val_rdy.recv

    s.dut.recv_from_cpu_ctrl_pkt.val //= 0
    s.dut.recv_from_cpu_ctrl_pkt.msg //= CtrlPktType()
    s.dut.send_to_ctrl_ring_ctrl_pkt.rdy //= 0

  def done(s):
    return s.src_from_tile_load_request_pkt_en_rdy.done() and \
           s.src_from_tile_load_response_pkt_en_rdy.done() and \
           s.src_from_tile_store_request_pkt_en_rdy.done() and \
           s.sink_to_tile_load_request_addr_en_rdy.done() and \
           s.sink_to_tile_load_response_data_en_rdy.done() and \
           s.sink_to_tile_store_request_addr_en_rdy.done() and \
           s.sink_to_tile_store_request_data_en_rdy.done() and \
           s.src_from_noc_val_rdy.done() and \
           s.sink_to_noc_val_rdy.done()

  def line_trace(s):
    return s.dut.line_trace()

#-------------------------------------------------------------------------
# run_rtl_sim
#-------------------------------------------------------------------------

def run_sim(test_harness, max_cycles = 20):

  # Create a simulator
  test_harness.elaborate()
  test_harness.apply( DefaultPassGroup() )
  test_harness.sim_reset()

  # Run simulation
  ncycles = 0
  print()
  print("{}:{}".format(ncycles, test_harness.line_trace()))
  while not test_harness.done() and ncycles < max_cycles:
    test_harness.sim_tick()
    ncycles += 1
    print("{}:{}".format(ncycles, test_harness.line_trace()))

  # Check timeout
  assert ncycles < max_cycles

  test_harness.sim_tick()
  test_harness.sim_tick()
  test_harness.sim_tick()

#-------------------------------------------------------------------------
# Test cases
#-------------------------------------------------------------------------

def mk_src_pkts(nterminals, lst):
  src_pkts = [[] for _ in range(nterminals)]
  src = 0
  for pkt in lst:
    if hasattr(pkt, 'fl_type'):
      if pkt.fl_type == 0:
        src = pkt.src
    else:
      src = pkt.src
    src_pkts[src].append(pkt)
  return src_pkts

data_nbits = 32
predicate_nbits = 1
DataType = mk_data(data_nbits, predicate_nbits)

nterminals = 4
CmdType = mk_bits(4)
ControllerIdType = mk_bits(clog2(nterminals))
num_ctrl_actions = 8
ctrl_mem_size = 16
num_ctrl_operations = 64
num_fu_inports = 2
num_fu_outports = 2
num_tile_inports = 4
num_tile_outports = 4
data_mem_size_global = 16
addr_nbits = clog2(data_mem_size_global)
AddrType = mk_bits(addr_nbits)

controller_id = 1

idTo2d_map = {
        0: [0, 0],
        1: [1, 0],
        2: [2, 0],
        3: [3, 0]
}

controller2addr_map = {
        0: [0, 3],
        1: [4, 7],
        2: [8, 11],
        3: [12, 15],
}

CtrlPktType = mk_ring_across_tiles_pkt(nterminals,
                                       num_ctrl_actions,
                                       ctrl_mem_size,
                                       num_ctrl_operations,
                                       num_fu_inports,
                                       num_fu_outports,
                                       num_tile_inports,
                                       num_tile_outports)

Pkt = mk_multi_cgra_noc_pkt(nterminals,
                            1,
                            addr_nbits = addr_nbits,
                            data_nbits = data_nbits,
                            predicate_nbits = predicate_nbits)

from_tile_load_request_pkts = [
    #   src  dst src_x src_y dst_x dst_y opq vc addr data predicate
    Pkt(0,   0,  0,    0,    0,    0,    0,  0, 1,   0,   1, ctrl_action = CMD_LOAD_REQUEST),
    Pkt(0,   0,  0,    0,    0,    0,    0,  0, 8,   0,   1, ctrl_action = CMD_LOAD_REQUEST),
    Pkt(0,   0,  0,    0,    0,    0,    0,  0, 13,  0,   1, ctrl_action = CMD_LOAD_REQUEST),
]

from_tile_load_response_pkts = [
    #   src  dst src_x src_y dst_x dst_y opq vc addr data predicate
    Pkt(0,   0,  0,    0,    0,    0,    0,  0, 11,  11,  1, ctrl_action = CMD_LOAD_RESPONSE),
    Pkt(0,   0,  0,    0,    0,    0,    0,  0, 14,  14,  1, ctrl_action = CMD_LOAD_RESPONSE),
    Pkt(0,   0,  0,    0,    0,    0,    0,  0, 12,  12,  1, ctrl_action = CMD_LOAD_RESPONSE),
]

from_tile_store_request_pkts = [
    #   src  dst src_x src_y dst_x dst_y opq vc addr data predicate
    Pkt(0,   0,  0,    0,    0,    0,    0,  0, 11,  110, 1, ctrl_action = CMD_STORE_REQUEST),
    Pkt(0,   0,  0,    0,    0,    0,    0,  0, 3,   300, 1, ctrl_action = CMD_STORE_REQUEST),
    Pkt(0,   0,  0,    0,    0,    0,    0,  0, 15,  150, 1, ctrl_action = CMD_STORE_REQUEST),
]

expected_to_tile_load_request_addr_msgs =  [AddrType(2)]
expected_to_tile_load_response_addr_msgs = [AddrType(8),     AddrType(9)]
expected_to_tile_load_response_data_msgs = [DataType(80, 1), DataType(90, 1)]
expected_to_tile_store_request_addr_msgs = [AddrType(5)]
expected_to_tile_store_request_data_msgs = [DataType(50, 1)]

from_noc_pkts = [
    #   src  dst src_x src_y dst_x dst_y opq vc addr data predicate
    Pkt(1,   0,  1,    0,    0,    0,    0,  0, 2,   0,   1, ctrl_action = CMD_LOAD_REQUEST),
    Pkt(2,   1,  2,    0,    1,    0,    0,  0, 8,   80,  1, ctrl_action = CMD_LOAD_RESPONSE),
    Pkt(0,   1,  0,    0,    1,    0,    0,  0, 5,   50,  1, ctrl_action = CMD_STORE_REQUEST),
    Pkt(0,   1,  0,    0,    1,    0,    0,  0, 9,   90,  1, ctrl_action = CMD_LOAD_RESPONSE),
]

expected_to_noc_pkts = [
    #   src  dst src_x src_y dst_x dst_y opq vc addr data predicate
    Pkt(1,   0,  1,    0,    0,    0,    0,  0, 1,   0,   1, ctrl_action = CMD_LOAD_REQUEST),
    Pkt(1,   2,  1,    0,    2,    0,    0,  0, 11,  11,  1, ctrl_action = CMD_LOAD_RESPONSE),
    Pkt(1,   2,  1,    0,    2,    0,    0,  0, 11,  110, 1, ctrl_action = CMD_STORE_REQUEST),

    Pkt(1,   2,  1,    0,    2,    0,    0,  0, 8,   0,   1, ctrl_action = CMD_LOAD_REQUEST),
    Pkt(1,   3,  1,    0,    3,    0,    0,  0, 14,  14,  1, ctrl_action = CMD_LOAD_RESPONSE),
    Pkt(1,   0,  1,    0,    0,    0,    0,  0, 3,   300, 1, ctrl_action = CMD_STORE_REQUEST),

    Pkt(1,   3,  1,    0,    3,    0,    0,  0, 13,  0,   1, ctrl_action = CMD_LOAD_REQUEST),
    Pkt(1,   3,  1,    0,    3,    0,    0,  0, 12,  12,  1, ctrl_action = CMD_LOAD_RESPONSE),
    Pkt(1,   3,  1,    0,    3,    0,    0,  0, 15,  150, 1, ctrl_action = CMD_STORE_REQUEST),
]

def test_simple(cmdline_opts):
  print("controller2addr_map: ", controller2addr_map)
  th = TestHarness(ControllerIdType, CtrlPktType,
                   CmdType, DataType,
                   AddrType, Pkt, controller_id,
                   from_tile_load_request_pkts,
                   from_tile_load_response_pkts,
                   from_tile_store_request_pkts,
                   # from_tile_load_response_data_msgs,
                   # from_tile_store_request_addr_msgs,
                   # from_tile_store_request_data_msgs,
                   expected_to_tile_load_request_addr_msgs,
                   expected_to_tile_load_response_data_msgs,
                   expected_to_tile_store_request_addr_msgs,
                   expected_to_tile_store_request_data_msgs,
                   from_noc_pkts,
                   expected_to_noc_pkts,
                   controller2addr_map, idTo2d_map,
                   nterminals)
  th.elaborate()
  th = config_model_with_cmdline_opts(th, cmdline_opts, duts = ['dut'])
  run_sim(th)
