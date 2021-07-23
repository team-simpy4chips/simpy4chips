""" In this example system we connect 6 Processors using two rings A and B where  A runs CW and be CCW.
    The ring is formed through 6 Routers that connect to each other to form a Ring. 
    Each of the routers connect directly to a single processor through 4 ports:
        - 2 ingress ports for traffic coming from the processor and joining the rings, one port per ring
        - 2 egress ports for traffic exiting the ring into one of the processor, one port per ring
    Each router connectes to 2 other routers to form the ring usin its egports rea and reb and its ingress ports
    ria, rib

    The implemented processor is dummy: it generates one packet on each of its ports addressed to one of the 5 other processors
    and sends it to to the router which forwards it to the final destination
    on its ingress port, the processor waits for packets to arrive then blocks for a random period of time (emulating some processing)
     before check for other incoming packets.

     Note: While each processor sending one packet is not likely to lock the ring and create deadlock (there is enough buffering)
     but because this is a ring, and because the traffic pattern is arbitrary, deadlocks are possible if the number of packets
     are increased such that the ring is full of packets and a cyclic dependency is created. The simulation will be stuck and
     analyzing the log will show where each packet is stuck. the number of packets can be increased in the runEgport() method
     of the Processor class
    """

from Platforms import Platform
from Components.BasicComponent import Unit
from Components.Buffers import FlowControlledBuffer
from Components.Pipelines import FlowControlledPipeline
from Components.Arbiters import RoundRobinCrossbar
from Components.Packets import BasePacket
import random
import logging
from simpy import Environment

class RouterEgressArbiter(RoundRobinCrossbar):
    
    def route(self, peekEvent):

        """ the peek event is the one that contains the inPort where a packet arrived 
            and the packet that arrived on it"""

        inPort=self.peekEvents.index(peekEvent) #the inPort at which the packet was detected
        pkt=peekEvent.value  # the original packet before 

        if pkt.f['destProc']==self.parent.routerID and inPort==0:

            outPort=1

        else:

            outPort=0

        #-----maintaining list of routed packets and their destinations---#
        self.routes[inPort]=outPort
        self.routedPktList[inPort]=pkt
        inPortName=self.toUp[inPort].name if self.inPorts>1 else self.toUp.name
        outPortName=self.toDn[outPort].name if self.outPorts>1 else self.toDn.name
        self.Log('DEBUG','Packet {} from {} was routed to {}'.format(pkt.uid, inPortName, outPortName))

    def unMask(self,pkt, outPort):

        #----Start of Request Unmasking Event---#

        return self.toDn[outPort].waitForCredit(pkt)

class Router(Unit):
    def __init__(self, env, name, parent=None,routerID=None):
        super().__init__(env, name, parent)

        self.routerID=routerID

        self.egports={}
        self.egports['rea']=FlowControlledPipeline(env,'rea',parent=self,depth=4,putBytesPerCycle=8,initCredits=4,monitorBW=True)
        self.egports['reb']=FlowControlledPipeline(env,'reb',parent=self,depth=4,putBytesPerCycle=8,initCredits=4,monitorBW=True)
        self.egports['pea']=FlowControlledPipeline(env,'pea',parent=self,depth=2,putBytesPerCycle=8,initCredits=2,monitorBW=True)
        self.egports['peb']=FlowControlledPipeline(env,'peb',parent=self,depth=2,putBytesPerCycle=8,initCredits=2,monitorBW=True)

        self.igports={}
        self.igports['ria']=FlowControlledBuffer(env,'ria',parent=self,capacity=4,monitorBW=True)
        self.igports['rib']=FlowControlledBuffer(env,'rib',parent=self,capacity=4,monitorBW=True)
        self.igports['pia']=FlowControlledBuffer(env,'pia',parent=self,capacity=2,monitorBW=True)
        self.igports['pib']=FlowControlledBuffer(env,'pib',parent=self,capacity=2,monitorBW=True)

        self.arbiters={}
        self.arbiters['rea']=RouterEgressArbiter(env,'reaArb',self,inPorts=2,outPorts=2,pushMode=True)
        self.arbiters['reb']=RouterEgressArbiter(env,'rebArb',self,inPorts=2,outPorts=2,pushMode=True)

        self.connectInternal()

    def connectInternal(self):

        for egport in self.egports:
            self.connect(fromUnit=self.egports[egport],toUnit=self, toPort=egport)

        for igport in self.igports:
            self.connect(fromUnit=self,toUnit=self.igports[igport], fromPort=igport)

        #connect the inputs of the arbiters
        self.connect(fromUnit=self.igports['ria'],toUnit=self.arbiters['rea'],toPort=0)
        self.connect(fromUnit=self.igports['pia'],toUnit=self.arbiters['rea'],toPort=1)

        self.connect(fromUnit=self.igports['rib'],toUnit=self.arbiters['reb'],toPort=0)
        self.connect(fromUnit=self.igports['pib'],toUnit=self.arbiters['reb'],toPort=1)

        #connect the outputs of the arbiters to the router egress ports
        self.connect(fromUnit=self.arbiters['rea'],toUnit=self.egports['rea'],fromPort=0)
        self.connect(fromUnit=self.arbiters['rea'],toUnit=self.egports['pea'],fromPort=1)

        self.connect(fromUnit=self.arbiters['reb'],toUnit=self.egports['reb'],fromPort=0)
        self.connect(fromUnit=self.arbiters['reb'],toUnit=self.egports['peb'],fromPort=1)

class Processor(Unit):

    def __init__(self, env, name, parent=None, processorID=None):
        super().__init__(env, name, parent)

        self.processorID=processorID


        self.egports={}
        self.egports['pea']=FlowControlledPipeline(env,'pea',parent=self,depth=2,putBytesPerCycle=8,initCredits=2,monitorBW=True)
        self.egports['peb']=FlowControlledPipeline(env,'peb',parent=self,depth=2,putBytesPerCycle=8,initCredits=2,monitorBW=True)

        self.igports={}
        self.igports['pia']=FlowControlledBuffer(env,'pia',parent=self,capacity=2,monitorBW=True)
        self.igports['pib']=FlowControlledBuffer(env,'pib',parent=self,capacity=2,monitorBW=True)

        self.connectInternal()

    def connectInternal(self):

        for egport in self.egports:
            self.connect(fromUnit=self.egports[egport],toUnit=self, toPort=egport)
        for igport in self.igports:
            self.connect(fromUnit=self,toUnit=self.igports[igport], fromPort=igport)

    def runIgPort(self,igport):

        while True:
            pkt= yield igport.get()
            yield self.env.timeout(random.randint(5,30))
            self.Log('INFO','Received Packet {} from Processor {}'.format(pkt.uid,pkt.f['srcProc']))

    def runEgPort(self,egport):

        for i in range(1):

            destProc=random.randint(0,5)
            while destProc==self.processorID:
                destProc=random.randint(0,5)
    
            pkt= BasePacket(fields={'srcProc':self.processorID,'destProc':destProc})
            yield egport.put(pkt)

    def run(self):
        self.env.process(self.runEgPort(self.egports['pea']))
        self.env.process(self.runEgPort(self.egports['peb']))
        self.env.process(self.runIgPort(self.igports['pia']))
        yield self.env.process(self.runIgPort(self.igports['pib']))

class Example1(Platform):

    def __init__(self,env,name,parent=None):
        super().__init__(env,name,parent)
        self.createSystem()
        self.unitConns()

    def connectP2R(self,processor,router):
        #Connect processor to router
        self.connect(fromUnit=processor,toUnit=router,fromPort='pea',toPort='pia')
        self.connect(fromUnit=processor,toUnit=router,fromPort='peb',toPort='pib')

        self.connect(fromUnit=router,toUnit=processor,fromPort='pea',toPort='pia')
        self.connect(fromUnit=router,toUnit=processor,fromPort='peb',toPort='pib')

    def connectR2R(self,router0,router1):
        #connect router to router
        self.connect(fromUnit=router0,toUnit=router1,fromPort='rea',toPort='ria')
        self.connect(fromUnit=router1,toUnit=router0,fromPort='reb',toPort='rib')

    def createSystem(self):

        for processorID in range(6):
            processor=Processor(self.env,'Processor'+str(processorID),self,processorID=processorID)
            router=Router(self.env,'Router'+str(processorID),self,routerID=processorID)
            self.insertUnit(processor)
            self.insertUnit(router)

            #connect the router to the attached processor:
            self.connectP2R(processor,router)

            if processorID>0:
                self.connectR2R(self.units['Router'+str(processorID-1)],router)

            if processorID==5:
                #close the ring
                self.connectR2R(router,self.units['Router0'])



logging.basicConfig(level=logging.INFO, filename="Examples/Ringof6.log", filemode='w')


env=Environment()

ex=Example1(env,'RingOf6')

env.run(until=10000)