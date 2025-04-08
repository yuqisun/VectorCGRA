"""
==========================================================================
ControllerRTL.py
==========================================================================
Controller for each CGRA. Mutiple controllers are interconnected in a
multi-cgra system.

Author : Cheng Tan
  Date : Dec 2, 2024
"""

from ..lib.basic.val_rdy.ifcs import RecvIfcRTL
from ..lib.basic.val_rdy.ifcs import SendIfcRTL
from ..lib.basic.val_rdy.queues import NormalQueueRTL
from ..lib.cmd_type import *
from ..lib.opt_type import *
from ..noc.PyOCN.pymtl3_net.channel.ChannelRTL import ChannelRTL
from ..noc.PyOCN.pymtl3_net.xbar.XbarBypassQueueRTL import XbarBypassQueueRTL


class ControllerRTL(Component):

  def construct(s,
                CgraIdType,
                IntraCgraPktType,
                InterCgraPktType,
                DataType,
                DataAddrType,
                multi_cgra_rows,
                multi_cgra_columns,
                num_tiles,
                controller2addr_map,
                idTo2d_map):

    assert(multi_cgra_columns >= multi_cgra_rows)

    # Used for calculating the x/y position.
    XType = mk_bits(max(clog2(multi_cgra_columns), 1))
    YType = mk_bits(max(clog2(multi_cgra_rows), 1))
    TileIdType = mk_bits(clog2(num_tiles + 1))

    # Interface
    s.controller_id = InPort(CgraIdType)

    # Request from/to other CGRA via NoC.
    s.recv_from_inter_cgra_noc = RecvIfcRTL(InterCgraPktType)
    s.send_to_inter_cgra_noc = SendIfcRTL(InterCgraPktType)

    s.recv_from_cpu_pkt = RecvIfcRTL(IntraCgraPktType)
    s.send_to_ctrl_ring_pkt = SendIfcRTL(IntraCgraPktType)

    s.recv_from_ctrl_ring_pkt = RecvIfcRTL(IntraCgraPktType)
    s.send_to_cpu_pkt = SendIfcRTL(IntraCgraPktType)

    # Request from/to tiles.
    s.recv_from_tile_load_request_pkt = RecvIfcRTL(InterCgraPktType)
    s.recv_from_tile_load_response_pkt = RecvIfcRTL(InterCgraPktType)
    s.recv_from_tile_store_request_pkt = RecvIfcRTL(InterCgraPktType)

    s.send_to_tile_load_request_addr = SendIfcRTL(DataAddrType)
    s.send_to_tile_load_request_src_cgra = SendIfcRTL(CgraIdType)
    s.send_to_tile_load_request_src_tile = SendIfcRTL(TileIdType)
    s.send_to_tile_load_response_data = SendIfcRTL(DataType)
    s.send_to_tile_store_request_addr = SendIfcRTL(DataAddrType)
    s.send_to_tile_store_request_data = SendIfcRTL(DataType)

    # Component
    s.recv_from_tile_load_request_pkt_queue = ChannelRTL(InterCgraPktType, latency = 1)
    s.recv_from_tile_load_response_pkt_queue = ChannelRTL(InterCgraPktType, latency = 1)
    s.recv_from_tile_store_request_pkt_queue = ChannelRTL(InterCgraPktType, latency = 1)

    s.send_to_tile_load_request_addr_queue = ChannelRTL(DataAddrType, latency = 1)
    s.send_to_tile_load_request_src_cgra_queue = ChannelRTL(CgraIdType, latency = 1)
    s.send_to_tile_load_request_src_tile_queue = ChannelRTL(TileIdType, latency = 1)
    s.send_to_tile_load_response_data_queue = ChannelRTL(DataType, latency = 1)
    s.send_to_tile_store_request_addr_queue = ChannelRTL(DataAddrType, latency = 1)
    s.send_to_tile_store_request_data_queue = ChannelRTL(DataType, latency = 1)

    # Crossbar with 4 inports (load and store requests towards remote
    # memory, load response from local memory, ctrl&data packet from cpu,
    # and command signal from inter-tile, i.e., intra-cgra, ring) and 1 
    # outport (only allow one request be sent out per cycle).
    s.crossbar = XbarBypassQueueRTL(InterCgraPktType, 5, 1)
    s.recv_from_cpu_pkt_queue = NormalQueueRTL(IntraCgraPktType)
    s.send_to_cpu_pkt_queue = NormalQueueRTL(IntraCgraPktType)

    # LUT for global data address mapping.
    addr_offset_nbits = 0
    s.addr2controller_lut = [Wire(CgraIdType) for _ in range(len(controller2addr_map))]
    # Assumes the address range is contiguous within one CGRA's SPMs.
    addr2controller_vector = [-1 for _ in range(len(controller2addr_map))]
    s.addr_base_items = len(controller2addr_map)
    for src_controller_id, address_range in controller2addr_map.items():
      begin_addr, end_addr = address_range[0], address_range[1]
      address_length = end_addr - begin_addr + 1
      assert (address_length & (address_length - 1)) == 0, f"{address_length} is not a power of 2."
      addr_offset_nbits = clog2(address_length)
      addr_base = begin_addr >> addr_offset_nbits
      assert addr2controller_vector[addr_base] == -1, f"address range [{begin_addr}, {end_addr}] overlaps with others."
      addr2controller_vector[addr_base] = CgraIdType(src_controller_id)

      s.addr2controller_lut[addr_base] //= CgraIdType(src_controller_id)

    # Constructs the idTo2d lut.
    s.idTo2d_x_lut= [Wire(XType) for _ in range(multi_cgra_columns * multi_cgra_rows)]
    s.idTo2d_y_lut= [Wire(YType) for _ in range(multi_cgra_columns * multi_cgra_rows)]
    for cgra_id in idTo2d_map:
      xy = idTo2d_map[cgra_id]
      s.idTo2d_x_lut[cgra_id] //= XType(xy[0])
      s.idTo2d_y_lut[cgra_id] //= YType(xy[1])

    # Connections
    # Requests towards others, 1 cycle delay to improve timing.
    s.recv_from_tile_load_request_pkt_queue.recv //= s.recv_from_tile_load_request_pkt
    s.recv_from_tile_load_response_pkt_queue.recv //= s.recv_from_tile_load_response_pkt
    s.recv_from_tile_store_request_pkt_queue.recv //= s.recv_from_tile_store_request_pkt

    # Requests towards local from others, 1 cycle delay to improve timing.
    s.send_to_tile_load_request_addr_queue.send //= s.send_to_tile_load_request_addr
    s.send_to_tile_load_request_src_cgra_queue.send //= s.send_to_tile_load_request_src_cgra
    s.send_to_tile_load_request_src_tile_queue.send //= s.send_to_tile_load_request_src_tile
    s.send_to_tile_load_response_data_queue.send //= s.send_to_tile_load_response_data
    s.send_to_tile_store_request_addr_queue.send //= s.send_to_tile_store_request_addr
    s.send_to_tile_store_request_data_queue.send //= s.send_to_tile_store_request_data

    # For control signals delivery from CPU to tiles.
    s.recv_from_cpu_pkt //= s.recv_from_cpu_pkt_queue.recv
    s.send_to_cpu_pkt //= s.send_to_cpu_pkt_queue.send

    @update
    def update_received_msg():
      kLoadRequestInportIdx = 0
      kLoadResponseInportIdx = 1
      kStoreRequestInportIdx = 2
      kFromCpuCtrlAndDataIdx = 3
      kFromInterTileRingIdx = 4

      s.send_to_cpu_pkt_queue.recv.val @= 0
      s.send_to_cpu_pkt_queue.recv.msg @= IntraCgraPktType(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) # , 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
      s.recv_from_ctrl_ring_pkt.rdy @= 0

      # For the command signal from inter-tile/intra-cgra control ring.
      s.crossbar.recv[kFromInterTileRingIdx].val @= s.recv_from_ctrl_ring_pkt.val
      s.recv_from_ctrl_ring_pkt.rdy @= s.crossbar.recv[kFromInterTileRingIdx].rdy
      s.crossbar.recv[kFromInterTileRingIdx].msg @= \
          InterCgraPktType(s.controller_id,
                           0, # dst is always 0 to align with the single outport of the crossbar.
                           s.idTo2d_x_lut[s.controller_id], # src_x
                           s.idTo2d_y_lut[s.controller_id], # src_y
                           s.idTo2d_x_lut[0], # dst_x
                           s.idTo2d_y_lut[0], # dst_y
                           s.recv_from_ctrl_ring_pkt.msg.src, # src_tile_id
                           num_tiles, # dst_tile_id
                           0, # opaque
                           0, # vc_id. No need to specify vc_id for self produce-consume pkt thanks to the additional VC buffer.
                           s.recv_from_ctrl_ring_pkt.msg.payload)
                           # s.recv_from_ctrl_ring_pkt.msg.addr, # addr
                           # 0, # data
                           # 0, # predicate
                           # 0, # payload
                           # s.recv_from_ctrl_ring_pkt.msg.ctrl_action, # ctrl_action
                           # 0, # ctrl_addr
                           # 0, # ctrl_operation
                           # 0, # ctrl_predicate
                           # 0, # ctrl_fu_in
                           # 0, # ctrl_routing_xbar_outport
                           # 0, # ctrl_fu_xbar_outport
                           # 0, # ctrl_routing_predicate_in
                           # 0, # ctrl_vector_factor_power
                           # 0, # ctrl_is_last_ctrl
                           # 0, # ctrl_write_reg_from
                           # 0, # ctrl_write_reg_idx
                           # 0, # ctrl_read_reg_from
                           # 0) # ctrl_read_reg_idx

      # For the load request from local tiles.
      s.crossbar.recv[kLoadRequestInportIdx].val @= s.recv_from_tile_load_request_pkt_queue.send.val
      s.recv_from_tile_load_request_pkt_queue.send.rdy @= s.crossbar.recv[kLoadRequestInportIdx].rdy
      s.crossbar.recv[kLoadRequestInportIdx].msg @= \
          InterCgraPktType(s.controller_id,
                           0,
                           s.idTo2d_x_lut[s.controller_id], # src_x
                           s.idTo2d_y_lut[s.controller_id], # src_y
                           0, # dst_x
                           0, # dst_y
                           s.recv_from_tile_load_request_pkt_queue.send.msg.src_tile_id, # src_tile_id
                           num_tiles, # dst_tile_id
                           0, # opaque
                           0, # vc_id
                           s.recv_from_tile_load_request_pkt_queue.send.msg.payload)
                           # s.recv_from_tile_load_request_pkt_queue.send.msg.addr, # addr
                           # 0, # data
                           # 1, # predicate
                           # 0, # payload
                           # CMD_LOAD_REQUEST, # ctrl_action
                           # 0, # ctrl_addr
                           # 0, # ctrl_operation
                           # 0, # ctrl_predicate
                           # 0, # ctrl_fu_in
                           # 0, # ctrl_routing_xbar_outport
                           # 0, # ctrl_fu_xbar_outport
                           # 0, # ctrl_routing_predicate_in
                           # 0, # ctrl_vector_factor_power
                           # 0, # ctrl_is_last_ctrl
                           # 0, # ctrl_write_reg_from
                           # 0, # ctrl_write_reg_idx
                           # 0, # ctrl_read_reg_from
                           # 0) # ctrl_read_reg_idx

      # For the store request from local tiles.
      s.crossbar.recv[kStoreRequestInportIdx].val @= s.recv_from_tile_store_request_pkt_queue.send.val
      s.recv_from_tile_store_request_pkt_queue.send.rdy @= s.crossbar.recv[kStoreRequestInportIdx].rdy
      s.crossbar.recv[kStoreRequestInportIdx].msg @= \
          InterCgraPktType(s.controller_id,
                           0,
                           s.idTo2d_x_lut[s.controller_id], # src_x
                           s.idTo2d_y_lut[s.controller_id], # src_y
                           0, # dst_x
                           0, # dst_y
                           s.recv_from_tile_store_request_pkt_queue.send.msg.src_tile_id, # src_tile_id
                           num_tiles, # dst_tile_id
                           0, # opaque
                           0, # vc_id
                           s.recv_from_tile_store_request_pkt_queue.send.msg.payload)
                           # s.recv_from_tile_store_request_pkt_queue.send.msg.addr, # addr
                           # s.recv_from_tile_store_request_pkt_queue.send.msg.data, # data
                           # s.recv_from_tile_store_request_pkt_queue.send.msg.predicate, # predicate
                           # 0, # payload
                           # CMD_STORE_REQUEST, # ctrl_action
                           # 0, # ctrl_addr
                           # 0, # ctrl_operation
                           # 0, # ctrl_predicate
                           # 0, # ctrl_fu_in
                           # 0, # ctrl_routing_xbar_outport
                           # 0, # ctrl_fu_xbar_outport
                           # 0, # ctrl_routing_predicate_in
                           # 0, # ctrl_vector_factor_power
                           # 0, # ctrl_is_last_ctrl
                           # 0, # ctrl_write_reg_from
                           # 0, # ctrl_write_reg_idx
                           # 0, # ctrl_read_reg_from
                           # 0) # ctrl_read_reg_idx

      # For the load response (i.e., the data towards other) from local memory.
      s.crossbar.recv[kLoadResponseInportIdx].val @= \
          s.recv_from_tile_load_response_pkt_queue.send.val
      s.recv_from_tile_load_response_pkt_queue.send.rdy @= s.crossbar.recv[kLoadResponseInportIdx].rdy
      s.crossbar.recv[kLoadResponseInportIdx].msg @= s.recv_from_tile_load_response_pkt_queue.send.msg
      # s.crossbar.recv[kLoadResponseInportIdx].msg @= \
      #     InterCgraPktType(0, # s.controller_id,
      #                0,
      #                0, # s.idTo2d_x_lut[s.controller_id], # src_x
      #                0, # s.idTo2d_y_lut[s.controller_id], # src_y
      #                s.idTo2d_x_lut[0], # dst_x
      #                s.idTo2d_y_lut[0], # dst_y
      #                0, # tile id
      #                0, # opaque
      #                0, # vc_id
      #                s.recv_from_tile_load_response_pkt_queue.send.msg.addr, # addr
      #                s.recv_from_tile_load_response_pkt_queue.send.msg.data, # data
      #                s.recv_from_tile_load_response_pkt_queue.send.msg.predicate, # predicate
      #                s.recv_from_tile_load_response_pkt_queue.send.msg.payload, # payload
      #                s.recv_from_tile_load_response_pkt_queue.send.msg.ctrl_action, # ctrl_action
      #                0, # ctrl_addr
      #                0, # ctrl_operation
      #                0, # ctrl_predicate
      #                0, # ctrl_fu_in
      #                0, # ctrl_routing_xbar_outport
      #                0, # ctrl_fu_xbar_outport
      #                0, # ctrl_routing_predicate_in
      #                0, # ctrl_vector_factor_power
      #                0, # ctrl_is_last_ctrl
      #                0, # ctrl_write_reg_from
      #                0, # ctrl_write_reg_idx
      #                0, # ctrl_read_reg_from
      #                0) # ctrl_read_reg_idx

      # For the ctrl and data preloading.
      s.crossbar.recv[kFromCpuCtrlAndDataIdx].val @= \
          s.recv_from_cpu_pkt_queue.send.val
      s.recv_from_cpu_pkt_queue.send.rdy @= s.crossbar.recv[kFromCpuCtrlAndDataIdx].rdy
      s.crossbar.recv[kFromCpuCtrlAndDataIdx].msg @= \
          InterCgraPktType(0, # src
                           s.recv_from_cpu_pkt_queue.send.msg.dst_cgra_id, # dst
                           0, # src_x
                           0, # src_y
                           s.idTo2d_x_lut[s.recv_from_cpu_pkt_queue.send.msg.dst_cgra_id], # dst_x
                           s.idTo2d_y_lut[s.recv_from_cpu_pkt_queue.send.msg.dst_cgra_id], # dst_y
                           0, # src_tile_id
                           s.recv_from_cpu_pkt_queue.send.msg.dst, # dst_tile_id 
                           0, # opaque
                           0, # vc_id
                           s.recv_from_cpu_pkt_queue.send.msg.payload) # , # vc_id
                           # s.recv_from_cpu_pkt_queue.send.msg.addr, # addr
                           # s.recv_from_cpu_pkt_queue.send.msg.data, # data
                           # s.recv_from_cpu_pkt_queue.send.msg.data_predicate, # predicate
                           # 0, # payload
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_action, # maybe CMD_CONFIG or CMD_CONST
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_addr, # ctrl_addr
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_operation, # ctrl_operation
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_predicate, # ctrl_predicate
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_fu_in, # ctrl_fu_in
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_routing_xbar_outport, # ctrl_routing_xbar_outport
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_fu_xbar_outport, # ctrl_fu_xbar_outport
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_routing_predicate_in, # ctrl_routing_predicate_in
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_vector_factor_power,
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_is_last_ctrl,
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_write_reg_from,
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_write_reg_idx,
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_read_reg_from,
                           # s.recv_from_cpu_pkt_queue.send.msg.ctrl_read_reg_idx)
      if s.recv_from_cpu_pkt_queue.send.val & \
         ((s.recv_from_cpu_pkt_queue.send.msg.payload.cmd == CMD_LOAD_REQUEST) | \
          (s.recv_from_cpu_pkt_queue.send.msg.payload.cmd == CMD_STORE_REQUEST)):
        # Updates the dest tile id for CPU issued LOAD and STORE request,
        # indicating they are from controller/CPU, and need to come back to
        # the controller (for LOAD response).
        s.crossbar.recv[kFromCpuCtrlAndDataIdx].msg.dst_tile_id @= num_tiles
        
      # TODO: For the other cmd types.


    # @update
    # def update_received_msg_from_noc():

      # Initiates the signals.
      s.send_to_tile_load_request_addr_queue.recv.val @= 0
      s.send_to_tile_load_request_src_cgra_queue.recv.val @= 0
      s.send_to_tile_load_request_src_tile_queue.recv.val @= 0
      s.send_to_tile_store_request_addr_queue.recv.val @= 0
      s.send_to_tile_store_request_data_queue.recv.val @= 0
      s.send_to_tile_load_response_data_queue.recv.val @= 0
      s.send_to_tile_load_request_addr_queue.recv.msg @= DataAddrType()
      s.send_to_tile_load_request_src_cgra_queue.recv.msg @= CgraIdType()
      s.send_to_tile_load_request_src_tile_queue.recv.msg @= TileIdType()
      s.send_to_tile_store_request_addr_queue.recv.msg @= DataAddrType()
      s.send_to_tile_store_request_data_queue.recv.msg @= DataType()
      s.send_to_tile_load_response_data_queue.recv.msg @= DataType()
      s.recv_from_inter_cgra_noc.rdy @= 0
      s.send_to_ctrl_ring_pkt.val @= 0
      s.send_to_ctrl_ring_pkt.msg @= IntraCgraPktType(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) # , 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

      # For the load request from NoC.
      received_pkt = s.recv_from_inter_cgra_noc.msg
      if s.recv_from_inter_cgra_noc.val:
        if s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_LOAD_REQUEST:
          s.send_to_tile_load_request_addr_queue.recv.val @= 1
          s.send_to_tile_load_request_src_cgra_queue.recv.val @= 1
          s.send_to_tile_load_request_src_tile_queue.recv.val @= 1

          if s.send_to_tile_load_request_addr_queue.recv.rdy:
            s.recv_from_inter_cgra_noc.rdy @= 1
            s.send_to_tile_load_request_addr_queue.recv.msg @= DataAddrType(received_pkt.payload.data_addr)
            s.send_to_tile_load_request_src_cgra_queue.recv.msg @= received_pkt.src
            # FIXME: for now, as we don't have src_tile_id, use dst_tile_id to represent it.
            s.send_to_tile_load_request_src_tile_queue.recv.msg @= received_pkt.dst_tile_id

        elif s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_STORE_REQUEST:
          s.send_to_tile_store_request_data_queue.recv.msg @= received_pkt.payload.data
          s.send_to_tile_store_request_addr_queue.recv.msg @= received_pkt.payload.data_addr
          s.send_to_tile_store_request_addr_queue.recv.val @= 1
          s.send_to_tile_store_request_data_queue.recv.val @= 1

          if s.send_to_tile_store_request_addr_queue.recv.rdy & \
             s.send_to_tile_store_request_data_queue.recv.rdy:
            s.recv_from_inter_cgra_noc.rdy @= 1

        elif s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_LOAD_RESPONSE:
          if s.recv_from_inter_cgra_noc.msg.dst_tile_id == num_tiles: # & \
            s.recv_from_inter_cgra_noc.rdy @= s.send_to_cpu_pkt_queue.recv.rdy
            s.send_to_cpu_pkt_queue.recv.val @= 1
            s.send_to_cpu_pkt_queue.recv.msg @= \
                IntraCgraPktType(s.recv_from_inter_cgra_noc.msg.src_tile_id, # src
                                 s.recv_from_inter_cgra_noc.msg.dst_tile_id, # dst
                                 s.recv_from_inter_cgra_noc.msg.src, # src_cgra_id
                                 s.recv_from_inter_cgra_noc.msg.dst, # src_cgra_id
                                 s.recv_from_inter_cgra_noc.msg.src_x, # src_cgra_x
                                 s.recv_from_inter_cgra_noc.msg.src_y, # src_cgra_y
                                 s.recv_from_inter_cgra_noc.msg.dst_x, # dst_cgra_x
                                 s.recv_from_inter_cgra_noc.msg.dst_y, # dst_cgra_y
                                 0, # opaque
                                 0, # vc_id
                                 s.recv_from_inter_cgra_noc.msg.payload)

                # IntraCgraPktType(s.recv_from_inter_cgra_noc.msg.dst,  # dst_cgra_id
                #                  0,  # src
                #                  s.recv_from_inter_cgra_noc.msg.dst_tile_id,  # dst
                #                  s.recv_from_inter_cgra_noc.msg.opaque,  # opaque
                #                  s.recv_from_inter_cgra_noc.msg.vc_id,  # vc_id
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_action,  # ctrl_action
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_addr,  # ctrl_addr
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_operation,  # ctrl_operation
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_predicate,  # ctrl_predicate
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_fu_in,  # ctrl_fu_in
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_routing_xbar_outport,  # ctrl_routing_xbar_outport
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_fu_xbar_outport,  # ctrl_fu_xbar_outport
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_routing_predicate_in,  # ctrl_routing_predicate_in
                #                  s.recv_from_inter_cgra_noc.msg.addr,  # addr
                #                  s.recv_from_inter_cgra_noc.msg.data,  # data
                #                  s.recv_from_inter_cgra_noc.msg.predicate,  # data_predicate
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_vector_factor_power,  # ctrl_vector_factor_power
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_is_last_ctrl,  # ctrl_is_last_ctrl
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_write_reg_from,  # ctrl_write_reg_from
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_write_reg_idx,  # ctrl_write_reg_idx
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_read_reg_from,  # ctrl_read_reg_from
                #                  s.recv_from_inter_cgra_noc.msg.ctrl_read_reg_idx)  # ctrl_read_reg_idx

          else:
            s.recv_from_inter_cgra_noc.rdy @= s.send_to_tile_load_response_data_queue.recv.rdy
            s.send_to_tile_load_response_data_queue.recv.msg @= received_pkt.payload.data
            s.send_to_tile_load_response_data_queue.recv.val @= 1

        elif s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_COMPLETE:
          s.recv_from_inter_cgra_noc.rdy @= s.send_to_cpu_pkt_queue.recv.rdy
          s.send_to_cpu_pkt_queue.recv.val @= 1
          s.send_to_cpu_pkt_queue.recv.msg @= \
              IntraCgraPktType(s.recv_from_inter_cgra_noc.msg.src_tile_id, # src
                               s.recv_from_inter_cgra_noc.msg.dst_tile_id, # dst
                               s.recv_from_inter_cgra_noc.msg.src, # src_cgra_id
                               s.recv_from_inter_cgra_noc.msg.dst, # src_cgra_id
                               s.recv_from_inter_cgra_noc.msg.src_x, # src_cgra_x
                               s.recv_from_inter_cgra_noc.msg.src_y, # src_cgra_y
                               s.recv_from_inter_cgra_noc.msg.dst_x, # dst_cgra_x
                               s.recv_from_inter_cgra_noc.msg.dst_y, # dst_cgra_y
                               0, # opaque
                               0, # vc_id
                               s.recv_from_inter_cgra_noc.msg.payload)


              # IntraCgraPktType(s.recv_from_inter_cgra_noc.msg.dst,  # dst_cgra_id
              #            0,  # src
              #            s.recv_from_inter_cgra_noc.msg.dst_tile_id,  # dst
              #            s.recv_from_inter_cgra_noc.msg.opaque,  # opaque
              #            s.recv_from_inter_cgra_noc.msg.vc_id,  # vc_id
              #            s.recv_from_inter_cgra_noc.msg.ctrl_action,  # ctrl_action
              #            s.recv_from_inter_cgra_noc.msg.ctrl_addr,  # ctrl_addr
              #            s.recv_from_inter_cgra_noc.msg.ctrl_operation,  # ctrl_operation
              #            s.recv_from_inter_cgra_noc.msg.ctrl_predicate,  # ctrl_predicate
              #            s.recv_from_inter_cgra_noc.msg.ctrl_fu_in,  # ctrl_fu_in
              #            s.recv_from_inter_cgra_noc.msg.ctrl_routing_xbar_outport,  # ctrl_routing_xbar_outport
              #            s.recv_from_inter_cgra_noc.msg.ctrl_fu_xbar_outport,  # ctrl_fu_xbar_outport
              #            s.recv_from_inter_cgra_noc.msg.ctrl_routing_predicate_in,  # ctrl_routing_predicate_in
              #            s.recv_from_inter_cgra_noc.msg.addr,  # addr
              #            s.recv_from_inter_cgra_noc.msg.data,  # data
              #            s.recv_from_inter_cgra_noc.msg.predicate,  # data_predicate
              #            s.recv_from_inter_cgra_noc.msg.ctrl_vector_factor_power,  # ctrl_vector_factor_power
              #            s.recv_from_inter_cgra_noc.msg.ctrl_is_last_ctrl,  # ctrl_is_last_ctrl
              #            s.recv_from_inter_cgra_noc.msg.ctrl_write_reg_from,  # ctrl_write_reg_from
              #            s.recv_from_inter_cgra_noc.msg.ctrl_write_reg_idx,  # ctrl_write_reg_idx
              #            s.recv_from_inter_cgra_noc.msg.ctrl_read_reg_from,  # ctrl_read_reg_from
              #            s.recv_from_inter_cgra_noc.msg.ctrl_read_reg_idx)  # ctrl_read_reg_idx


        elif (s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_CONFIG) | \
             (s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_CONFIG_PROLOGUE_FU) | \
             (s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_CONFIG_PROLOGUE_FU_CROSSBAR) | \
             (s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_CONFIG_PROLOGUE_ROUTING_CROSSBAR) | \
             (s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_CONFIG_TOTAL_CTRL_COUNT) | \
             (s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_CONFIG_COUNT_PER_ITER) | \
             (s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_CONST) | \
             (s.recv_from_inter_cgra_noc.msg.payload.cmd == CMD_LAUNCH):
          s.recv_from_inter_cgra_noc.rdy @= s.send_to_ctrl_ring_pkt.rdy
          s.send_to_ctrl_ring_pkt.val @= s.recv_from_inter_cgra_noc.val
          s.send_to_ctrl_ring_pkt.msg @= \
              IntraCgraPktType(s.recv_from_inter_cgra_noc.msg.src_tile_id, # src
                               s.recv_from_inter_cgra_noc.msg.dst_tile_id, # dst
                               s.recv_from_inter_cgra_noc.msg.src, # src_cgra_id
                               s.recv_from_inter_cgra_noc.msg.dst, # src_cgra_id
                               s.recv_from_inter_cgra_noc.msg.src_x, # src_cgra_x
                               s.recv_from_inter_cgra_noc.msg.src_y, # src_cgra_y
                               s.recv_from_inter_cgra_noc.msg.dst_x, # dst_cgra_x
                               s.recv_from_inter_cgra_noc.msg.dst_y, # dst_cgra_y
                               0, # opaque
                               0, # vc_id
                               s.recv_from_inter_cgra_noc.msg.payload)

          # s.send_to_ctrl_ring_pkt.msg @= \
          #     IntraCgraPktType(s.recv_from_inter_cgra_noc.msg.dst,  # dst_cgra_id
          #                0,  # src
          #                s.recv_from_inter_cgra_noc.msg.dst_tile_id,  # dst
          #                s.recv_from_inter_cgra_noc.msg.opaque,  # opaque
          #                s.recv_from_inter_cgra_noc.msg.vc_id,  # vc_id
          #                s.recv_from_inter_cgra_noc.msg.ctrl_action,  # ctrl_action
          #                s.recv_from_inter_cgra_noc.msg.ctrl_addr,  # ctrl_addr
          #                s.recv_from_inter_cgra_noc.msg.ctrl_operation,  # ctrl_operation
          #                s.recv_from_inter_cgra_noc.msg.ctrl_predicate,  # ctrl_predicate
          #                s.recv_from_inter_cgra_noc.msg.ctrl_fu_in,  # ctrl_fu_in
          #                s.recv_from_inter_cgra_noc.msg.ctrl_routing_xbar_outport,  # ctrl_routing_xbar_outport
          #                s.recv_from_inter_cgra_noc.msg.ctrl_fu_xbar_outport,  # ctrl_fu_xbar_outport
          #                s.recv_from_inter_cgra_noc.msg.ctrl_routing_predicate_in,  # ctrl_routing_predicate_in
          #                s.recv_from_inter_cgra_noc.msg.addr,  # addr
          #                s.recv_from_inter_cgra_noc.msg.data,  # data
          #                s.recv_from_inter_cgra_noc.msg.predicate,  # data_predicate
          #                s.recv_from_inter_cgra_noc.msg.ctrl_vector_factor_power,  # ctrl_vector_factor_power
          #                s.recv_from_inter_cgra_noc.msg.ctrl_is_last_ctrl,  # ctrl_is_last_ctrl
          #                s.recv_from_inter_cgra_noc.msg.ctrl_write_reg_from,  # ctrl_write_reg_from
          #                s.recv_from_inter_cgra_noc.msg.ctrl_write_reg_idx,  # ctrl_write_reg_idx
          #                s.recv_from_inter_cgra_noc.msg.ctrl_read_reg_from,  # ctrl_read_reg_from
          #                s.recv_from_inter_cgra_noc.msg.ctrl_read_reg_idx)  # ctrl_read_reg_idx

        # else:
        #   # TODO: Handle other cmd types.
        #   assert(False)

    @update
    def update_sending_to_noc_msg():
      s.send_to_inter_cgra_noc.val @= s.crossbar.send[0].val
      s.crossbar.send[0].rdy @= s.send_to_inter_cgra_noc.rdy
      s.send_to_inter_cgra_noc.msg @= s.crossbar.send[0].msg
      if (s.crossbar.send[0].msg.payload.cmd == CMD_LOAD_REQUEST) | \
         (s.crossbar.send[0].msg.payload.cmd == CMD_STORE_REQUEST):
        addr_dst_id = s.addr2controller_lut[trunc(s.crossbar.send[0].msg.payload.data_addr >> addr_offset_nbits, CgraIdType)]
        s.send_to_inter_cgra_noc.msg.dst @= addr_dst_id
        s.send_to_inter_cgra_noc.msg.dst_x @= s.idTo2d_x_lut[addr_dst_id]
        s.send_to_inter_cgra_noc.msg.dst_y @= s.idTo2d_y_lut[addr_dst_id]

  def line_trace(s):
    recv_from_cpu_pkt_str = "recv_from_cpu_pkt: " + str(s.recv_from_cpu_pkt.msg)
    recv_from_cpu_pkt_queue_str = "recv_from_cpu_pkt_queue.send: " + str(s.recv_from_cpu_pkt_queue.send.msg)
    crossbar_recv_str = "crossbar_recv.val:" + str(s.crossbar.recv[3].val) + " crossbar_recv.rdy:" + str(s.crossbar.recv[3].rdy) + " crossbar_recv.msg: " + str(s.crossbar.recv[3].msg)
    send_to_ctrl_ring_pkt_str = "send_to_ctrl_ring_pkt.val:" + str(s.send_to_ctrl_ring_pkt.val) + " send_to_ctrl_ring_pkt: " + str(s.send_to_ctrl_ring_pkt.msg) + " send_to_ctrl_ring_pkt.rdy:" + str(s.send_to_ctrl_ring_pkt.rdy)
    recv_from_tile_load_request_pkt_str = "recv_from_tile_load_request_pkt: " + str(s.recv_from_tile_load_request_pkt.msg)
    recv_from_tile_load_response_pkt_str = "recv_from_tile_load_response_pkt: " + str(s.recv_from_tile_load_response_pkt.msg)
    recv_from_tile_store_request_pkt_str = "recv_from_tile_store_request_pkt: " + str(s.recv_from_tile_store_request_pkt.msg)
    crossbar_str = "crossbar: {" + s.crossbar.line_trace() + "}"
    send_to_tile_load_request_addr_str = "send_to_tile_load_request_addr: " + str(s.send_to_tile_load_request_addr.msg)
    send_to_tile_store_request_addr_str = "send_to_tile_store_request_addr: " + str(s.send_to_tile_store_request_addr.msg)
    send_to_tile_store_request_data_str = "send_to_tile_store_request_data: " + str(s.send_to_tile_store_request_data.msg)
    recv_from_noc_str ="recv_from_noc_pkt.val: " + str(s.recv_from_inter_cgra_noc.val) + " recv_from_noc_pkt.msg: " + str(s.recv_from_inter_cgra_noc.msg) + " recv_from_noc_pkt.rdy: " + str(s.recv_from_inter_cgra_noc.rdy)
    send_to_noc_str = "send_to_noc_pkt: " + str(s.send_to_inter_cgra_noc.msg) + "; rdy: " + str(s.send_to_inter_cgra_noc.rdy) + "; val: " + str(s.send_to_inter_cgra_noc.val)
    return f'{recv_from_cpu_pkt_str} || {recv_from_cpu_pkt_queue_str} || {crossbar_recv_str} ||  {send_to_ctrl_ring_pkt_str} || {recv_from_tile_load_request_pkt_str} || {recv_from_tile_load_response_pkt_str} || {recv_from_tile_store_request_pkt_str} || {crossbar_str} || {send_to_tile_load_request_addr_str} || {send_to_tile_store_request_addr_str} || {send_to_tile_store_request_data_str} || {recv_from_noc_str} || {send_to_noc_str}\n'
