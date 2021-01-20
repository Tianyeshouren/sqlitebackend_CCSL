from flask import jsonify

from tools import is_number, HtmlHeader, HTMLFooter
from z3 import z3
from z3 import *
from CCSL import CCSL
import time
import random
import json

class SMT:
    def __init__(self, ccslcons, labid, bound=0, period=0, realPeroid=0):
        self.id = labid
        self.response = {}
        self.result = 'unsat'
        self.exetime  = 0
        ccsl = CCSL(ccslcons)
        tmp = ccsl.workOnCCSL()
        self.oldClocks = tmp["oldClocks"]
        self.newClocks = tmp["newClocks"]
        self.newCCSLConstraintList = tmp["newCCSLConstraintList"]
        self.oldCCSLConstraintList = tmp["oldCCSLConstraintList"]
        self.parameter = tmp["parameter"]
        self.bound = bound
        self.period = period
        self.realPeroid = realPeroid
        self.parameterRange = []
        self.solver = z3.SolverFor("AUFLIRA")
        z3.set_param("smt.random_seed", random.randint(100,1000000))
        self.solver.set(unsat_core=True)
        # self.solver.set(produce_models=True)
        # self.solver.set(print_success=False)
        self.printParameter = {}
        self.tickStep = {}
        self.n = z3.Int("n")
        if self.period > 0:
            self.k = z3.Int("k")
            self.l = z3.Int("l")
            self.p = z3.Int("p")
        self.tickDict = {}
        self.historyDict = {}
        self.Tick_result = {}
        self.cnt = 0

    def RealProduce(self):
        """
        This function is used to do some configruation of the model,such as the bound and the period.
        :return:
        """
        if self.bound > 0:
            self.solver.add(self.n == self.bound)
        # If the model want you to work out a model with period
        if self.period > 0:
            self.solver.add(self.l >= 1)
            if self.realPeroid == 0: #the period is not a fixed value.
                self.solver.add(self.p > 0,self.p <= self.n)
            else:#the period is not a fixed value.
                self.solver.add(self.p == self.realPeroid)
            self.solver.add(self.k == (self.l + self.p))
            self.solver.add(self.k <= self.n)

    def addTickSMT(self):
        for each in self.newClocks:
            self.tickDict["t_%s" % (each)] = z3.Function("t_%s" % (each), z3.IntSort(), z3.BoolSort())
            tick = self.tickDict["t_%s" % (each)]
            if self.bound > 0:
                y = z3.Int("y")
                if self.period > 0:
                    for y in range(1, self.bound + 1):
                        self.solver.add(
                            z3.Implies(
                                y >= self.k,
                                tick((y - self.l) % self.p + self.l) == tick(y)
                            )
                        )
                    # self.solver.add(
                    #     z3.ForAll(y,z3.Implies(
                    #         z3.And(y >= self.k,y <= self.bound),
                    #         tick((y - self.l) % self.p + self.l) == tick(y))))
            elif self.bound == 0:
                x = z3.Int("x")
                if self.period > 0:
                    y = z3.Int("y")
                    self.solver.add(
                        z3.ForAll(y,z3.Implies(
                            y >= self.k,
                            tick((y - self.l) % self.p + self.l) == tick(y))))
        clockListTmp = []
        x = z3.Int("x")
        for each in self.tickDict.keys():
            tick = self.tickDict[each]
            clockListTmp.append(tick(x))
        if self.bound == 0:
            self.solver.add(z3.ForAll(x, z3.Implies(x >= 1, z3.Or(clockListTmp))))
        else:
            for i in range(1,self.bound + 1):
                tmp = []
                for tick in self.tickDict.values():
                    tmp.append(tick(i))
                self.solver.add(
                    z3.Or(tmp)
                )
            # self.solver.add(z3.ForAll(x, z3.Implies(z3.And(x >= 1, x <= self.n), z3.Or(clockListTmp))))

    def addHistory(self):
        for clock in self.newClocks:
            history = None
            tick = self.tickDict["t_%s" % (clock)]
            if ("h_%s" % (clock)) not in self.historyDict.keys():
                history = z3.Function("h_%s" % (clock), z3.IntSort(), z3.IntSort())
                self.historyDict["h_%s" % (clock)] = history
            else:
                history = self.historyDict["h_%s" % (clock)]
            # self.solver.add(history(0) == z3.IntVal(0))
            self.solver.add(history(1) == z3.IntVal(0))
            if self.bound > 0:
                # If the bound is finite, we define the history of the clock with a fixed bound.
                for i in range(1, self.bound + 1):
                    self.solver.add(z3.If(tick(i),
                                          history(i + 1) == history(i) + 1,
                                          history(i + 1) == history(i)))
                    # self.solver.add(z3.If(tick(i),
                    #                       history(i + 1) == history(i) + 1,
                    #                       history(i + 1) == history(i)))
            elif self.bound == 0:
                x = z3.Int("x")
                # If the bound is infinite, we define the history of the clock infinitely.
                self.solver.add(z3.ForAll(x, z3.Implies(x >= 1,
                                            z3.If(tick(x),history(x + 1) == history(x) + 1,
                                            history(x + 1) == history(x)))))

    def addTickStep(self, clock):
        tick = self.tickDict["t_%s" % (clock)]
        history = self.historyDict["h_%s" % (clock)]
        if "s_%s" % (clock) not in self.tickStep.keys():
            tickStep = z3.Function("s_%s" % (clock), z3.IntSort(), z3.IntSort())
            self.tickStep["s_%s" % (clock)] = tickStep
            if self.bound > 0:
                x = z3.Int("x")
                # If the bound is infinite, we define the history of the clock infinitely.
                for i in range(1, self.bound + 1):
                    self.solver.add(
                        z3.Implies(
                            tick(i),
                            tickStep(history(i) + 1) == i
                        ))
            elif self.bound == 0:
                x = z3.Int("x")
                # If the bound is infinite, we define the history of the clock infinitely.
                self.solver.add(z3.ForAll(x, z3.Implies(z3.And(x >= 1,tick(x)),
                    tickStep(history(x) + 1) == x)))

    def addTickForever(self):
        """
        Adding a clock msec, which ticks every step, represents the real-time.
        :return:
        """
        if "msec" in self.oldClocks:
            tick = self.tickDict["t_%s" %("msec")]
            if self.bound > 0:
                for i in range(1,self.bound + 1):
                    self.solver.add(tick(i) == True)
            else:
                x = z3.Int("x")
                self.solver.add(z3.ForAll(x, z3.Implies(x >= 1, tick(x) == True)))

    def addOriginSMTConstraints(self):
        """
        Realize to transfer the CCSL constraints into SMT formula.
        :return:
        """
        cnt = 0
        for each in self.newCCSLConstraintList:
            if each[0] == "<" and len(each) == 3:
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[2])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1,self.bound + 2):
                        self.solver.add(
                            z3.Implies(
                                history1(i) == history2(i),
                                z3.Not(tick2(i))
                            )
                        )
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #     z3.And(x >= 1, x <= self.n, history1(x) == history2(x)),
                    #     z3.Not(tick2(x)))))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                        z3.And(x >= 1, history1(x) == history2(x)),
                        z3.Not(tick2(x)))))

            elif each[0] == "<" and len(each) == 4:
                tick1 = self.tickDict["t_%s" % (each[1])]
                delay = each[2]
                tick2 = self.tickDict["t_%s" % (each[3])]
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[3])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 2):
                        self.solver.add(
                            z3.Implies(
                                history2(i) - history1(i) == delay,
                                z3.Not(tick2(i))
                            )
                        )
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #     z3.And(x >= 1, x <= self.n, history2(x) - history1(x) == delay),
                    #     z3.Not(tick2(x)))))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                        z3.And(x >= 1, history2(x) - history1(x) == delay),
                        z3.Not(tick2(x)))))

            elif each[0] == "≤":
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[2])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 2):
                        self.solver.add(
                            history1(i) >= history2(i)
                        )
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #     z3.And(x >= 1, x <= self.n + 1),
                    #     history1(x) >= history2(x))))
                else:
                    self.solver.add(z3.ForAll(x,z3.Implies(
                        x >= 1,
                        history1(x) >= history2(x))))

            elif each[0] == "⊆":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 1):
                        self.solver.add(
                            z3.Implies(
                                tick1(i),
                                tick2(i)
                            )
                        )
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #     z3.And(x >= 1, x <= self.n, tick1(x)),
                    #     tick2(x))))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                        z3.And(x >= 1, tick1(x)),
                        tick2(x))))

            elif each[0] == "#":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 1):
                        self.solver.add(
                            z3.Or(z3.Not(tick1(i)), z3.Not(tick2(i)))
                        )
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #     z3.And(x >= 1, x <= self.n),
                    #     z3.Or(z3.Not(tick1(x)), z3.Not(tick2(x))))))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                        x >= 1,
                        z3.Or(z3.Not(tick1(x)), z3.Not(tick2(x))))))

            elif each[0] == "+":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                tick3 = self.tickDict["t_%s" % (each[3])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 1):
                        self.solver.add(
                                tick1(i) ==
                                z3.Or(tick2(i), tick3(i))
                        )
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #         z3.And(x >= 1, x <= self.n),
                    #         tick1(x) == z3.Or(tick2(x), tick3(x)))))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                            x >= 1,
                            tick1(x) == z3.Or(tick2(x), tick3(x)))))

            elif each[0] == "-":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                tick3 = self.tickDict["t_%s" % (each[3])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 1):
                        self.solver.add(
                                tick1(i) ==
                                z3.And(tick2(i), z3.Not(tick3(i)))
                        )
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #         z3.And(x >= 1, x <= self.n),
                    #         tick1(x) == z3.Or(tick2(x), tick3(x)))))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                            x >= 1,
                            tick1(x) == z3.And(tick2(x), z3.Not(tick3(x))))))

            elif each[0] == "*":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                tick3 = self.tickDict["t_%s" % (each[3])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 1):
                        self.solver.add(tick1(i) ==z3.And(tick2(i), tick3(i)))
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #         z3.And(x >= 1, x <= self.n),
                    #         tick1(x) == z3.And(tick2(x), tick3(x)))))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                            x >= 1,
                            tick1(x) == z3.And(tick2(x), tick3(x)))))

            elif each[0] == "∧":
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[2])]
                history3 = self.historyDict["h_%s" % (each[3])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 2):
                        self.solver.add(
                            history1(i) == z3.If(history2(i) >= history3(i), history2(i), history3(i))
                        )
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #     z3.And(x >= 1, x <= self.n + 1),
                    #     history1(x) == z3.If(history2(x) >= history3(x),history2(x),history3(x)))))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                        x >= 1,
                        history1(x) == z3.If(history2(x) >= history3(x),history2(x),history3(x)))))

            elif each[0] == "∨":
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[2])]
                history3 = self.historyDict["h_%s" % (each[3])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 2):
                        self.solver.add(
                            history1(i) == z3.If(history2(i) <= history3(i), history2(i), history3(i))
                        )
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #     z3.And(x >= 1, x <= self.n + 1),
                    #     history1(x) == z3.If(history2(x) <= history3(x), history2(x), history3(x)))))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                        x >= 1,
                        history1(x) == z3.If(history2(x) <= history3(x), history2(x), history3(x)))))

            elif each[0] == "$":
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[2])]
                delay = z3.IntVal(int(each[3]))
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 2):
                        self.solver.add(
                            history1(i) == z3.If(history2(i) >= delay, history2(i) - delay, 0)
                        )
                    # self.solver.add(z3.ForAll(x, z3.Implies(
                    #     z3.And(x >= 1, x <= self.n + 1),
                    #     history1(x) == z3.If(history2(x) >= delay,history2(x) - delay,0))))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                        x >= 1,
                        history1(x) == z3.If(history2(x) >= delay,history2(x) - delay,0))))

            elif each[0] == "on":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                tick3 = self.tickDict["t_%s" % (each[4])]
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[2])]
                history3 = self.historyDict["h_%s" % (each[4])]
                self.addTickStep(each[1])
                self.addTickStep(each[2])
                self.addTickStep(each[4])
                tickStep1 = self.tickStep["s_%s" % (each[1])]
                tickStep2 = self.tickStep["s_%s" % (each[2])]
                tickStep3 = self.tickStep["s_%s" % (each[4])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, int(each[3]) + 1):
                        self.solver.add(z3.Not(tick1(i)))
                    for i in range(int(each[3]) + 1, self.bound + 1):
                        t = []
                        for j in range(1, i - int(each[3]) + 1):
                            t.append(z3.And(
                                tick2(j), history3(i) - history3(j) == int(each[3])
                            ))
                        self.solver.add(z3.And(tick3(i),z3.Or(t)) == tick1(i))
                    for i in range(1, self.bound + 2):
                        self.solver.add(history2(i) >= history1(i))
                    # self.solver.add(z3.ForAll(x,z3.Implies(
                    #     z3.And(x > 0,x <= self.n + 1),
                    #     history2(x) >= history1(x)
                    # )))
                    for i in range(1, self.bound + 1):
                        self.solver.add(z3.Implies(tick1(i), tick3(i)))
                    # self.solver.add(
                    #     z3.ForAll(x, z3.Implies(
                    #         z3.And(x > 0, x <= history1(self.bound + 1)),
                    #         history3(tickStep2(x)) - history3(tickStep1(x)) == int(each[3])
                    # )))
                    # for i in range(self.bound + 1):
                    #     self.solver.add(history2(i) >= history1(i))
                    # for i in range(self.bound):
                    #     self.solver.add(
                    #         z3.Implies(
                    #             tick1(i), tick3(i)
                    #         )
                    #     )
                    # for i in range(self.bound + 1):
                    #     self.solver.add(
                    #         history3(tickStep1(i)) - history3(tickStep2(i)) == int(each[3])
                    #     )

                    # self.solver.add(z3.ForAll(x, z3.And(
                    #     z3.Implies(z3.And(x >= 1, x <= history1(self.bound + 1),tick2(x)),
                    #         tick1(tickStep3(history3(x) + int(each[3])))
                    #     ))))
                else:
                    self.solver.add(z3.ForAll(x, z3.And(
                        z3.Implies(x >= 1, history2(x) >= history1(x)))))
                    self.solver.add(z3.ForAll(x, z3.And(
                        z3.Implies(z3.And(x >= 1,tick1(x)), tick3(x)))))
                    self.solver.add(z3.ForAll(x, z3.And(
                        z3.Implies(x >= 1,(history3(tickStep1(x)) - history3(tickStep2(x)) == int(each[3])))
                            )))
            elif each[0] == "∝":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[2])]

                if is_number(each[3]):
                    k = z3.Int("k_%s" % (cnt))
                    self.solver.add(k >= 0, k < int(each[3]))
                    cnt += 1
                    # right = z3.And(tick2(x), history2(x) > 0, (history2(x)) % z3.IntVal(each[3]) == 0)
                else:
                    period = z3.Int("%s" % each[3])
                    tmp = self.parameter[each[3]]
                    self.printParameter[each[3]] = period
                    k = z3.Int("k_%s" % (cnt))
                    self.solver.add(k >= 0, k < period)
                    # right = z3.And(tick2(x), history2(x) >= 0, (history2(x) + k) % period == 0)
                    self.solver.add(period >= int(tmp[2]))
                    self.solver.add(period <= int(tmp[3]))
                    cnt += 1
                if self.bound > 0:
                    if is_number(each[3]):
                        for i in range(1, self.bound + 1):
                            self.solver.add(
                                z3.And(tick2(i), history2(i) >= 0,
                                       (history2(i) + k) % z3.IntVal(each[3]) == 0) == tick1(i)
                            )
                    else:
                        for i in range(1, self.bound + 1):
                            self.solver.add(
                                z3.And(tick2(i), history2(i) >= 0, (history2(x) + k) % period == 0) == tick1(i)
                            )

            elif each[0] == "!∝":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[2])]
                if is_number(each[3]):
                    for i in range(1, self.bound + 1):
                        self.solver.add(
                            z3.And(tick2(i), history2(i) >= 0, history2(i) % z3.IntVal(each[3]) == 0) == tick1(i)
                        )
                else:
                    period = z3.Int("%s" % each[3])
                    tmp = self.parameter[each[3]]
                    self.printParameter[each[3]] = period
                    # right = z3.And(tick2(x), history2(x) >= 0, (history2(x) + k) % period == 0)
                    self.solver.add(period >= int(tmp[2]))
                    self.solver.add(period <= int(tmp[3]))
                    cnt += 1
                    for i in range(1, self.bound + 1):
                        self.solver.add(
                            z3.And(tick2(i), history2(i) >= 0, history2(i) % period == 0) == tick1(i)
                        )

            elif each[0] == "☇":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                tick3 = self.tickDict["t_%s" % (each[3])]
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[2])]
                history3 = self.historyDict["h_%s" % (each[3])]
                self.addTickStep(each[1])
                self.addTickStep(each[3])
                tickStep1 = self.tickStep["s_%s" % (each[1])]
                tickStep3 = self.tickStep["s_%s" % (each[3])]
                x = z3.Int("x")
                if self.bound > 0:
                    self.solver.add(
                        z3.ForAll(
                            x,
                            z3.Implies(
                                z3.And(x >= 2, x <= history3(self.bound + 1)),
                                tick1(tickStep1(x)) == (history2(tickStep3(x)) - history2(tickStep3(x - 1)) >= 1))
                        )
                    )
                else:
                    self.solver.add(
                        z3.ForAll(
                            x,
                            z3.Implies(
                                x >= 2,
                                z3.And(
                                    tick1(tickStep1(x)),
                                    history2(tickStep3(x)) - history2(tickStep3(x - 1)) >= 1)
                            )
                        )
                    )

            elif each[0] == "==":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 1):
                        self.solver.add(tick1(i) == tick2(i))
                else:
                    self.solver.add(z3.ForAll(x, z3.Implies(
                        x >= 1,
                        tick1(x) == tick2(x)
                    )))
            elif each[0] == "⋈±":
                tick1 = self.tickDict["t_%s" % (each[1])]
                tick2 = self.tickDict["t_%s" % (each[2])]
                history1 = self.historyDict["h_%s" % (each[1])]
                history2 = self.historyDict["h_%s" % (each[2])]
                self.addTickStep(each[1])
                self.addTickStep(each[2])
                tickStep1 = self.tickStep["s_%s" % (each[1])]
                tickStep2 = self.tickStep["s_%s" % (each[2])]

                lower = int(each[3]) - int(each[4])
                upper = int(each[3]) + int(each[4])
                x = z3.Int("x")
                if self.bound > 0:
                    for i in range(1, self.bound + 2):
                        self.solver.add(z3.Implies(tick1(i), history1(tickStep2(history2(i) + upper)) -
                                                   history1(tickStep2(history2(i) + lower)) == 1))
                        self.solver.add(z3.Implies(z3.And(i >= 2, i <= history1(self.bound + 1)),
                                                   z3.And(
                                                       (history2(tickStep1(i)) - history2(tickStep1(i - 1)) >= lower),
                                                       (history2(tickStep1(i)) - history2(tickStep1(i - 1)) <= upper)
                                                   )
                                                   )
                                        )
                else:
                    self.solver.add(
                        z3.ForAll(
                            x,
                            z3.Implies(
                                x >= 2,
                                z3.And(
                                    (history2(tickStep1(x)) - history2(tickStep1(x - 1)) >= lower),
                                    (history2(tickStep1(x)) - history2(tickStep1(x - 1)) <= upper)
                                )
                            )
                        )
                    )

    def getWorkOut(self):
        if self.period > 0:
            print("k:\t%s" %self.solver.model()[self.k])
            print("l:\t%s" %self.solver.model()[self.l])
            print("p:\t%s" %self.solver.model()[self.p])
        model = self.solver.model()
        # echart_Html
        bd = []
        clk = []
        ycatalog = []
        sche = []
        for i in range(1, self.bound + 2):
            bd.append(i)
        sbd = str(bd)
        print(sbd)
        index = 0;
        tickstr = '['
        for each in self.oldClocks:
            clk.append(str(each))
            ycatalog.append(str(each) + '_idle')
            ycatalog.append(str(each) + '_tick')
            dict = {}
            dict['name'] = str(each)
            dict['type'] = 'line'
            dict['step'] = 'end'
            # for each in self.newClocks:
            tick = self.tickDict["t_%s" % each]
            TmpTickList = []
            for i in range(1, self.bound + 1):
                if model.eval(tick(i)) == True:
                    TmpTickList.append(str(each)+'_tick')
                else:
                    TmpTickList.append(str(each)+'_idle')
            if model.eval(tick(self.bound)) == True:
                TmpTickList.append(str(each)+'_tick')
            else:
                TmpTickList.append(str(each)+'_idle')
            index = index + 2
            dict['data'] = TmpTickList
            sche.append(dict)
            j = json.dumps(dict)
            tickstr += str(j) + ',\n'
        tickstr = tickstr[:-2]
        tickstr += ']'
        sclk = str(clk)
        sycatalog = str(ycatalog)
        print(sycatalog)
        print(sclk)
        print(tickstr)
        print(sche)

        output_html_echart = ''
        with open(r'echar1.txt', 'r', encoding='utf-8') as f:
            output_html_echart = f.read()
            f.close()
        output_html_echart = output_html_echart.replace("CLK-DATA", sclk,1);
        output_html_echart =output_html_echart.replace("X-DATA",sbd,1);
        output_html_echart =output_html_echart.replace("Y-DATA",sycatalog,1);
        output_html_echart =output_html_echart.replace("SCHE-DATA",tickstr,1 );

        with open(r'output_echar.html', 'w', encoding='utf-8') as f:
            f.write(output_html_echart)
            f.close()

        for each in self.oldClocks:
        # for each in self.newClocks:
            TmpTickList = []
            tick = self.tickDict["t_%s" %each]
            for i in range(1,self.bound + 1):
                if model.eval(tick(i)) == True:
                    TmpTickList.append(i)
            self.Tick_result[each] = TmpTickList
        if len(self.printParameter.keys()) == 0:
            for each in self.Tick_result.keys():
                print(each, self.Tick_result[each])
        t = {}
        for each in self.printParameter.keys():
            t[each] = model.eval(self.printParameter[each])
            print(each,model.eval(self.printParameter[each]))
        print()
        self.parameterRange.append(t)

        self.response = {
            'CLK': clk,
            'X': bd,
            'Y': ycatalog,
            'SCHE': sche
        }



    def outPutTickByHTML(self):
        html = "<div id='dpic'><ul><li class='name'></li>"
        for each in range(1, self.bound + 1):
            html += "<li>%s</li>" % (each)
        html += "</ul>"
        d = sorted(self.Tick_result.keys())
        # for each in self.Tick_result.keys():
        for each in d:
            if each != "msec":
                html += "<ul><li class='name'>%s</li>" % (each)
                cnt = 0
                res = ""
                for i in range(1, self.bound + 1):
                    if i in self.Tick_result[each]:
                        if i - 1 in self.Tick_result[each] or i - 1 == 0:
                            html += "<li class='up'></li>"
                        else:
                            html += "<li class='upl'></li>"
                    else:
                        if i - 1 not in self.Tick_result[each] or i - 1 == 0:
                            html += "<li class='down'></li>"
                        else:
                            html += "<li class='downl'></li>"
                    if i in self.Tick_result[each]:
                        cnt += 1
                    res += "<li>%s</li>" % (cnt)
                html += "</ul>"
        if "msec" in d:
            each = "msec"
            html += "<ul><li class='name'>%s</li>" % (each)
            cnt = 0
            res = ""
            for i in range(1, self.bound + 1):
                if i in self.Tick_result[each]:
                    if i - 1 in self.Tick_result[each] or i - 1 == 0:
                        html += "<li class='up'></li>"
                    else:
                        html += "<li class='upl'></li>"
                else:
                    if i - 1 not in self.Tick_result[each] or i - 1 == 0:
                        html += "<li class='down'></li>"
                    else:
                        html += "<li class='downl'></li>"
                res += "<li>%s</li>" % (cnt)
                if i in self.Tick_result[each]:
                    cnt += 1
            html += "</ul>"
            html += "<ul><li class='name'>H</li>" + res + "</ul>"


        # for w in self.oldCCSLConstraintList:
        # # for w in self.newCCSLConstraintList:
        #     if w[0] != "∈":
        #         # html += "<ul><li class='name'>%s</li>" % (w)
        #         for each in w[1:]:
        #             if is_number(str(each)) is False and str(each) not in self.parameter.keys():
        #                 html += "<ul><li class='name'>%s</li>" % (each)
        #                 cnt = 0
        #                 res = ""
        #                 for i in range(1, self.bound + 1):
        #                     if i in self.Tick_result[each]:
        #                         if i - 1 in self.Tick_result[each] or i - 1 == 0:
        #                             html += "<li class='up'></li>"
        #                         else:
        #                             html += "<li class='upl'></li>"
        #                     else:
        #                         if i - 1 not in self.Tick_result[each] or i - 1 == 0:
        #                             html += "<li class='down'></li>"
        #                         else:
        #                             html += "<li class='downl'></li>"
        #                     if i - 1 in self.Tick_result[each]:
        #                         cnt += 1
        #                     res += "<li class='history'>%s</li>" % (cnt)
        #                 html += "</ul>"
        #                 html += "<ul><li class='name'>H%s</li>" % (each) + res + "</ul>"
        #         html += "<ul><li></li></ul></ul>"
        #         html += "</ul>"
        html += "<hr>"
        html += "</div>"
        return html

    def addExtraConstraints(self):
        model = self.solver.model()
        ExtraConstraints = []
        # if len(self.printParameter.keys()) == 0:
        #     for each in self.newClocks:
        #         self.tickDict["t_%s" % (each)] = z3.Function("t_%s" % (each), z3.IntSort(), z3.BoolSort())
        #         for i in range(1, self.bound + 1):
        #             tmp = self.tickDict["t_%s" % (each)]
        #             ExtraConstraints.append(tmp(i) != model.eval(tmp(i)))
        for each in self.printParameter.keys():
            ExtraConstraints.append(self.printParameter[each] != model.eval(self.printParameter[each]))
        self.solver.add(z3.Or(ExtraConstraints))

    def work(self):
        self.RealProduce()
        self.addTickSMT()
        self.addHistory()
        self.addTickForever()
        self.addOriginSMTConstraints()
        #ticktimes = self.historyDict["h_%s" %("ef")]
        #self.solver.add(ticktimes(self.bound+1) > 0 )
        #tick = self.tickDict["t_%s" %("T5s1")]
        #self.solver.add(tick(1))
        f = open("out.smt2","w")
        f.write(self.solver.to_smt2())
        f.flush()
        f.close()

    def getAllSchedule(self):
        self.work()
        i = 0
        start = time.time()
        state = self.solver.check()
        self.exetime = time.time() - start
        print(time.time() - start)
        print(state)
        while state == z3.sat:
            self.result = 'sat'
            self.getWorkOut()
            # html = "<h1>%s</h1>" % (i)
            html = ""
            html += self.outPutTickByHTML()
            self.addExtraConstraints()
            i += 1
            # if len(self.printParameter.keys()) == 0:
            #     if i == 10:
            #         break
            outpath = "metadata/" + self.id + "/bd-" + str(self.bound)+".html"
            with open(outpath, "a+", encoding='utf-8') as f:
                f.write(html)
                f.flush()
                f.close()
            state = self.solver.check()
            print(state)
            # if i == 10:
            #     break
            print(time.time() - start)

        if len(self.printParameter.keys()) != 0:
            print(self.parameterRange)
        print(time.time() - start)

    def getResult(self):
        return self.result

    def getTime(self):
        return self.exetime
    def getJson(self):
        return self.response


if __name__ == "__main__":

    bound = 20
    ss = ''
    with open('ccsl.txt', 'r', encoding='UTF-8') as f:
        ss = f.read()
    smt = SMT(ss, labid= 'test',bound=bound, period=0, realPeroid=0)
    smt.getAllSchedule()

