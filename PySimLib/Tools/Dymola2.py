# -*- coding: utf-8 -*-
"""
Created on Thu Feb 15 11:40:39 2018

@author: jmoeckel

This reproduced the functionality of Tools.Dymola but avoids a dde Server and
uses the Dymola-Python interface instead - much more stability. 
"""

from PySimLib import Log, Platform
from PySimLib.Config import *
from PySimLib.Mat.Mat import Mat
from PySimLib.Tools.ModelicaTool import ModelicaTool


class Dymola2(ModelicaTool):

    __dymolaIsOpen = False
    __openFiles = {}
    __solverMap = {
        'deabm': 1,
        'lsodar': 4,
        'dassl': 8
        # TODO THE REST
    }

    # Constructor
    def __init__(this):
        ModelicaTool.__init__(this)

        if(GetBoolConfigValue("Dymola2", "SimByExe") == False):
            print("Warning: You're using Dymola with a reduced feature set. Models may won't be simulated altough they're working directly in Dymola (independent of PySimLib). Please make sure you've read and understood section 2.6.4 of the PySimLib user Guide - specifically the part about the 'SimByExe' flag.")

    # Private methods
    def __CheckIfModelIsCompiled(this, mdl):
        from PySimLib.Exceptions.UncompiledModelException import UncompiledModelException

        # check if model is compiled
        if(not this._FileExists(this.__GetExeFilePath(mdl))):
            raise UncompiledModelException(mdl, this)

    def __DeleteUnnecessaryFiles(this):
        this._DeleteFile("alistlog.txt")
        this._DeleteFile("buildlog.txt")
        this._DeleteFile("dsfinal.txt")
        this._DeleteFile("dsin.txt")
        this._DeleteFile("dslog.txt")
        this._DeleteFile("dsmodel.c")
        this._DeleteFile("dymosim.exe")
        this._DeleteFile("dymosim.exp")
        this._DeleteFile("dymosim.lib")

    def __EnsureDymolaIsOpen(this):
        if(not Dymola2.__dymolaIsOpen):
            import sys
            sys.path.append(r'C:\Program Files\Dymola 2018 FD01\Modelica\Library\python_interface\dymola.egg')
            from dymola.dymola_interface import DymolaInterface
            from PySimLib import Platform

            Dymola2.__interface = DymolaInterface()
            print('Dymola-Interface opened')
            Dymola2.__dymolaIsOpen = True

            #Platform.Execute([GetConfigValue("Dymola2", "PathExe")], False)

            Dymola2.__interface.ExecuteCommand("OutputCPUtime:=true;")
        else:
            print('Dymola is still open')

    def __GetExeFilePath(this, mdl):
        from PySimLib import Platform

        return mdl.outputDir + os.sep + mdl.outputName + Platform.GetExeFileExtension()

    def __GetInitFilePath(this, mdl):
        return mdl.outputDir + os.sep + mdl.outputName + "_in.mat"

    def __GetSimInitFilePath(this, sim):
        mdl = sim.GetModel()
        return mdl.simDir + os.sep + str(sim.GetSimNumber()) + "_in.mat"

    def __MapSolver(this, solver):
        for key in Dymola2.__solverMap:
            if(solver.Matches(key)):
                return Dymola2.__solverMap[key]

        raise Exception("Illegal solver '" + str(solverNumber) + "'")

    def __OpenFile(this, mdl, fileName):
        path = os.path.join(mdl.simDir, fileName)

        if(path not in Dymola2.__openFiles):
            suc = Dymola2.__interface.openModel(path)
            print(path)
            print(suc)
            Dymola2.__openFiles[path] = True

    def __ReadVarsFromMat(this, names, values, varTypeFilter):
        from PySimLib.VariableDescriptor import VariableDescriptor

        result = {}

        for i in range(0, names.GetNumberOfStrings()):
            if(values.GetValue(4, i) in varTypeFilter):
                varDesc = VariableDescriptor()
                varDesc.start = values.GetValue(1, i)
                result[names.GetString(i)] = varDesc

        return result

    def __ReverseMapSolver(this, solverNumber):
        from PySimLib import FindSolver

        solverNumber = int(solverNumber)
        for key in Dymola2.__solverMap:
            if(Dymola2.__solverMap[key] == solverNumber):
                return FindSolver(key)

        raise Exception("Illegal solver number '" + str(solverNumber) + "'")

    def __WriteInit(this, sim):
        from PySimLib.Mat.OutputStream import OutputStream
        from PySimLib.Mat.MatrixTypeEvaluator import TYPE_INT32

        mdl = sim.GetModel()

        mat = Mat()
        mat.Load(this.__GetInitFilePath(mdl))

        # set experiment values
        experiment = mat.GetMatrix("experiment")
        experiment.SetValue(0, 0, sim.startTime)
        experiment.SetValue(0, 1, sim.stopTime)
        experiment.SetValue(0, 3, sim.solver.numberOfIntervals)
        experiment.SetValue(0, 4, sim.solver.tolerance)
        experiment.SetValue(0, 6, this.__MapSolver(sim.solver))
        # TODO: STEPSIZE

        # set variable start values
        names = mat.GetMatrix("initialName")
        values = mat.GetMatrix("initialValue")
        for i in range(0, names.GetNumberOfStrings()):
            name = names.GetString(i)
                     
            if name in sim.variables:  
                if(sim.variables[name].start is not None):
                    value = sim.variables[name].start
                    values.SetValue(1, i, value)
                    
            elif name in sim.parameters:                
                if sim.parameters[name] is not None:
                    value = sim.parameters[name]
                    values.SetValue(1, i, value)
                
            else:
                continue

        # write output
        file = open(this.__GetSimInitFilePath(sim), "wb")
        stream = OutputStream(file)
        # mat.Write(stream);

        # we need to set precision values for the matrices or dymola wont accept the input
        settings = mat.GetMatrix("settings")

        settings.SetDesiredOutputPrecision(TYPE_INT32)

        mat.GetMatrix("initialDescription").SetString(0, "Dymola")

        # we need to write the matrices in the exact order or dymola can't read the file
        mat.GetMatrix("Aclass").Write("Aclass", stream)
        mat.GetMatrix("experiment").Write("experiment", stream)
        mat.GetMatrix("method").Write("method", stream)
        settings.Write("settings", stream)
        mat.GetMatrix("initialName").Write("initialName", stream)
        mat.GetMatrix("initialValue").Write("initialValue", stream)
        mat.GetMatrix("initialDescription").Write("initialDescription", stream)

        file.close()

    def Close(this):
        if(Dymola2.__interface is not None):
            Dymola2.__interface.close()
            Dymola2.__interface = None
            Dymola2.__dymolaIsOpen = False
            Dymola2.__openFiles = {}
            print('Dymola-Interface closed.')

    def Compile(this, mdl):
        from PySimLib import Platform

        this.__EnsureDymolaIsOpen()

        # open all needed mo files
        for x in mdl.GetFiles():
            this.__OpenFile(mdl, x)

        # go to sim dir
        Dymola2.__interface.cd(mdl.simDir)

        # simulate to run model
        suc = Dymola2.__interface.translateModel(mdl.GetModelicaClassString())

        if not suc:
            this.Close()
            print('translating the model did not work out too well:\n{}'.format(Dymola2.__interface.getLastError()))
            
        this._EnsureOutputFolderExists(mdl)

        # Convert the dsin
        args = [
            GetConfigValue("Dymola2", "PathAlist"),
            "-b",
            mdl.simDir + os.sep + "dsin.txt",
            this.__GetInitFilePath(mdl)
        ]
        Platform.Execute(args)

        # this._DeleteFile("dsres.mat");

        # Rename important files
        this._RenameFile("dymosim" + Platform.GetExeFileExtension(), this.__GetExeFilePath(mdl))

        this.__DeleteUnnecessaryFiles()
        
        this.Close()

    def GetCompatibleSolvers(this):
        from PySimLib import FindSolver

        solvers = []

        for key in Dymola2.__solverMap:
            solvers.append(FindSolver(key))

        return solvers

    def GetName(this):
        return "Dymola2"

    def ReadInit(this, mdl):
        this.__CheckIfModelIsCompiled(mdl)

        initMat = Mat()
        initMat.Load(this.__GetInitFilePath(mdl))

        # read parameters
        varTypeFilter = {
            1,  # parameters
        }

        parameters = this.__ReadVarsFromMat(initMat.GetMatrix("initialName"), initMat.GetMatrix("initialValue"), varTypeFilter)
        for name in parameters:
            mdl.parameters[name] = parameters[name].start

        # read variables
        varTypeFilter = {
            2,  # state variable
            # 3,  # state derrivatives
            6,  # auxiliary variable
        }

        mdl.variables = this.__ReadVarsFromMat(initMat.GetMatrix("initialName"), initMat.GetMatrix("initialValue"), varTypeFilter)

        # read experiment values
        experiment = initMat.GetMatrix("experiment")
        mdl.startTime = experiment.GetValue(0, 0)
        mdl.stopTime = experiment.GetValue(0, 1)
        mdl.solver = this.__ReverseMapSolver(experiment.GetValue(0, 6))
        # sim.solver.stepSize = TODO: ???
        mdl.solver.tolerance = experiment.GetValue(0, 4)

    def Simulate(this, sim):
        mdl = sim.GetModel()

        # paths
        dsinPaths = mdl.simDir + os.sep + "dsin.txt"

        # error checks
        this.__CheckIfModelIsCompiled(mdl)

        this._EnsureResultFolderExists(mdl)

        # prepare init file
        this.__WriteInit(sim)

        # simulate
        if(GetBoolConfigValue("Dymola2", "SimByExe")):
            from PySimLib import Log, Platform

            args = [this.__GetExeFilePath(mdl), this.__GetSimInitFilePath(sim)]
            Platform.Execute(args, True, mdl.simDir)
        else:
            from PySimLib import Log, Platform
            # convert back to dsin
            args = [
                GetConfigValue("Dymola2", "PathAlist"),
                "-a",
                this.__GetSimInitFilePath(sim),
                dsinPaths
            ]
            # Platform.Execute(args);

            # run
            this.__EnsureDymolaIsOpen()
            Dymola2.__interface.simulateModel(mdl.GetModelicaClassString(True, sim),
                                              startTime=sim.startTime,
                                              stopTime=sim.stopTime,
                                              method=sim.solver.GetName(),
                                              tolerance=sim.solver.tolerance)

            # we always need to close the model, so that dymola recompiles it
            # jm: Tut es doch ?
            # Dymola2.__ddeConversation.Exec("closeModel();")

            # delete dsin
            this._DeleteFile(dsinPaths)

        failed = False
        if(this._FileExists("failure")):
            failed = True

        # keep things clean
        this._DeleteFile("status");
        this._DeleteFile("success");
        this._DeleteFile("failure");
        
        if(failed):
            this._DeleteFile("dsres.mat")
            from PySimLib.Exceptions.SimulationFailedException import SimulationFailedException
            raise SimulationFailedException(sim, 'Dymola2')

        this._DeleteFile(this.__GetSimInitFilePath(sim));

        # rename results
        this._RenameFile(mdl.simDir + os.sep + "dsres.mat", this._GetSimResultFilePath(sim))

        this.__DeleteUnnecessaryFiles()

    # Class functions
    def IsAvailable():
        return HasConfigValue("Dymola2", "PathExe") and HasConfigValue("Dymola2", "StartupDelay") and HasConfigValue("Dymola2", "PathAlist") and HasConfigValue("Dymola2", "SimByExe")
