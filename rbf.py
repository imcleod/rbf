#!/usr/bin/python

"""@package parser
Parser for Board XML Template

Parses provided XML Template
"""

import os
import subprocess
import sys
import platform
import logging
import uuid
import errno
from xml.dom.minidom import parse
import xml.dom.minidom
from rbfutils import RbfUtils

def printUsage():
   logging.info("./rbf.py <parse|build> <xmlTemplate.xml>")

def initLogging():
    """Initialize Logging"""   
    logFormatter = logging.Formatter("[%(levelname)-5.5s]  %(message)s")
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.INFO)
    if os.path.exists("rbf.log"):
        os.remove("rbf.log")
    fileHandler = logging.FileHandler("rbf.log")
    fileHandler.setFormatter(logFormatter)    
    rootLogger.addHandler(fileHandler)
    
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler) 
    
def checkCommandExistsAccess(commandList):
    """Checks if commands in the command list are present in the system & are executable"""
    osPathList = os.environ["PATH"].split(":");
    notFoundList = []
    notExecList = []
    for command in commandList:
        commandExists = False
        for path in osPathList:
            fullPath = path+"/"+command
            if os.path.exists(fullPath):
                commandExists = True
                break
        if commandExists:
            if os.access(fullPath,os.X_OK):
                continue
            else:
                notExecList.append(command)
        else:
            notFoundList.append(command)
    
    
    if len(notFoundList) != 0:
        notFoundString=""
        for command in notFoundList:
            notFoundString = notFoundString + command + ", "

        notFoundString = notFoundString[0:-2]
        logging.error("Commands Not Found: "+ notFoundString)
    
    if len(notExecList) != 0:
        notExecString=""
        for command in notExecList:
            notExecString = notExecString + command + ", "

        notExecString = notExecString[0:-2]
        logging.error("Commands Not Executable: "+ notExecString)
        
    if len(notFoundList) == 0 and len(notExecList) == 0:
        return True
    else:
        return False


class BoardTemplateParser():
    """BoardTemplateParser Class.
    
    Parses XML Template and performs required actions on image file
    """
    INDEX, SIZE, BEGIN, PTYPE, FS, MOUNTPOINT, UUID = range (0,7)
    INCORRECT_ARGUMENTS, ERROR_PARSING_XML, ERROR_IMAGE_FILE, INVALID_PARTITION_DATA, NO_PACKAGES, NO_KERNEL_TYPE, INCORRECT_REPOSITORY, IMAGE_EXISTS, NO_UBOOT, LOGICAL_PART_ERROR, PRIMARY_PART_ERROR, PARTITION_SIZES_ERROR, FSTAB_ERROR, CLEANUP_ERROR, NOT_ROOT, COMMANDS_NOT_FOUND, SYS_MKFS_COMMANDS_NOT_FOUND, NO_FIRMWARE_FOUND, TEMPLATE_NOT_FOUND, TOTAL_PARTITIONS_ERROR = range(100,120)    
    LOOP_DEVICE_EXISTS, FALLOCATE_ERROR, PARTED_ERROR, LOOP_DEVICE_CREATE_ERROR, PARTITION_DOES_NOT_EXIST, MOUNTING_ERROR, WRITE_REPO_ERROR, COPY_KERNEL_ERROR, COPY_FIRMWARE_ERROR, RPMDB_INIT_ERROR, GROUP_INSTALL_ERROR, PACKAGE_INSTALL_ERROR, ETC_OVERLAY_ERROR, ROOT_PASS_ERROR, SELINUX_ERROR, BOARD_SCRIPT_ERROR, FINALIZE_SCRIPT_ERROR, EXTLINUXCONF_ERROR, NO_ETC_OVERLAY, LOOP_DEVICE_DELETE_ERROR = range (200,220)
    RbfScriptErrors = { LOOP_DEVICE_EXISTS: "LOOP_DEVICE_EXISTS: Specified Loop Device Already Exists. Check losetup -l",
                        FALLOCATE_ERROR : "FALLOCATE_ERROR: Error While Creating Image File",
                        PARTED_ERROR: "PARTED_ERROR: Could Not Partition Image",
                        LOOP_DEVICE_CREATE_ERROR: "LOOP_DEVICE_CREATE_ERROR: Could Not Create Loop Device. Device Might Be Busy. Check \"losetup -l\"",
                        PARTITION_DOES_NOT_EXIST: "PARTITION_DOES_NOT_EXIST: Could Not Find Specified Partition",
                        MOUNTING_ERROR: "MOUNTING_ERROR: Could Not Mount Partitions",
                        WRITE_REPO_ERROR: "WRITE_REPO_ERROR: Could Not Write Repo Files",
                        COPY_KERNEL_ERROR: "COPY_KERNEL_ERROR: Could Not Copy Kernel",
                        COPY_FIRMWARE_ERROR: "COPY_FIRMWARE_ERROR: Could Not Copy Firmware",
                        RPMDB_INIT_ERROR: "RPMDB_INIT_ERROR: Could Not Init RPM DB",
                        GROUP_INSTALL_ERROR: "GROUP_INSTALL_ERROR: Error Installing Some Package Groups",
                        PACKAGE_INSTALL_ERROR: "PACKAGE_INSTALL_ERROR: Error Installing Some Packages",
                        ETC_OVERLAY_ERROR: "ETC_OVERLAY_ERROR: Could Not Copy /etc Overlay",
                        ROOT_PASS_ERROR: "ROOT_PASS_ERROR: Could Not Set Empty Root Pass",
                        SELINUX_ERROR: "SELINUX_ERROR: Could Not Set SELINUX Status",
                        BOARD_SCRIPT_ERROR: "BOARD_SCRIPT_ERROR: Error In Board Script",
                        FINALIZE_SCRIPT_ERROR: "FINALIZE_SCRIPT_ERROR: Error In Finalize Script",
                        EXTLINUXCONF_ERROR: "EXTLINUXCONF_ERROR: Error Creating /boot/extlinux/extlinux.conf",
                        NO_ETC_OVERLAY: "No Etc Overlay Found",
                        LOOP_DEVICE_DELETE_ERROR: "Could Not Delete Loop Device. Device Might Be Busy. Check \"losetup -l\""  }
   
    def __init__(self, action, xmlTemplate):
        """Constructor for BoardTemplateParser"""
        logging.info("Xml Template: "+xmlTemplate)
        self.action = action
        self.imagePath = ""
        self.xmlTemplate = xmlTemplate
        self.boardDom = None
        self.workDir = ""
        self.packageGroups = []
        self.packages = []
        self.rbfUtils = RbfUtils();
        self.imageData = []
        self.stockKernels = []
        self.repoNames = []
        self.rbfScript = open("rbf.sh","w")
        self.initramfsScript = None
        self.cleanupScript = None
        
    def __del__(self):
        """Destructor for BoardTemplateParser"""
        self.rbfScript.close()    
    
    def getTagValue(self, dom, domTag):
        """Extracts Tag Value from DOMTree"""
        xmlTag = dom.getElementsByTagName(domTag)
        for x in xmlTag:
            return x.childNodes[0].data
            
    def parseTemplate(self):
        """Parses xmlTemplate"""
        logging.info("Parsing: "+ self.xmlTemplate)
        try:
            self.boardDom = xml.dom.minidom.parse(self.xmlTemplate)            
        except:
            logging.error("Error Parsing XML Template File")
            sys.exit(BoardTemplateParser.ERROR_PARSING_XML)
        
        self.boardName = self.getTagValue(self.boardDom,"board")        
        self.workDir = self.getTagValue(self.boardDom,"workdir")        
        self.finalizeScript = self.getTagValue(self.boardDom,"finalizescript")
        self.loopDevice = subprocess.check_output(['losetup','-f']).strip()
        self.selinuxConf = self.getTagValue(self.boardDom,"selinux")
        self.etcOverlay = self.getTagValue(self.boardDom,"etcoverlay")
        self.linuxDistro = self.getTagValue(self.boardDom,"distro")
        self.extlinuxConf = self.getTagValue(self.boardDom,"extlinuxconf")
        self.hostName = self.getTagValue(self.boardDom,"hostname")
        self.rootFiles = self.getTagValue(self.boardDom,"rootfiles")
        self.ubootPath = self.getTagValue(self.boardDom,"uboot")
        self.firmwareDir = self.getTagValue(self.boardDom,"firmware")
        logging.info("Successfully Parsed Board Template For: " + self.boardName)
    
    def getShellExitString(self,exitCode):
        """Generates Shell Exit command. Used to check successful command execution"""
        return "if [ $? != 0 ]; then exit " + str(exitCode) + "; fi\n\n"
    
    def getShellErrorString(self,exitCode):
        """Generates Shell Error command. Used to check successful command execution"""
        return "if [ $? != 0 ]; then echo [INFO ]  " + self.RbfScriptErrors[exitCode] + ";  read -p \"Press Enter To Continue\"; fi\n\n"
        
    def createImage(self):
        """Creates Image File"""        
        self.rbfScript.write("echo [INFO ]   $0 Detacing Loop Device If Busy: " + self.loopDevice+"\n")
        self.rbfScript.write(self.delDeviceIfExists(self.loopDevice))
        logging.info("Creating Image File")
        imageDom = self.boardDom.getElementsByTagName("image")[0]
        if imageDom.hasAttribute("size") and imageDom.hasAttribute("size") and imageDom.hasAttribute("size"):
            self.imageSize = imageDom.getAttribute("size")
            imageType = imageDom.getAttribute("type")
            self.imagePath = imageDom.getAttribute("path")
            if self.imageSize[len(self.imageSize)-1] == "M" or self.imageSize[len(self.imageSize)-1] == "G":
                logging.info("Creating Image: " + self.imageSize + " " + imageType + " " + self.imagePath)
            else:
                 logging.error("Invalid Image Size: " + self.imageSize)
                 sys.exit(BoardTemplateParser.ERROR_IMAGE_FILE)   
        else:
            logging.error("No image tag found or image tag incomplete.")
            sys.exit(BoardTemplateParser.ERROR_IMAGE_FILE)
    
        self.imageSize = self.rbfUtils.getImageSizeInM(self.imageSize)

        if os.path.exists(self.imagePath):
            logging.error("Image Already Exists")
            sys.exit(BoardTemplateParser.IMAGE_EXISTS)
        
        self.rbfScript.write("echo [INFO ]    $0 Creating " + self.imagePath + "\n")
        self.rbfScript.write("fallocate -l " + self.imageSize + " " + self.imagePath + " &>> rbf.log \n")
        self.rbfScript.write(self.getShellExitString(BoardTemplateParser.FALLOCATE_ERROR))
    
    def verifyPartitionSizes(self,partitionsDom):
        """Checks if partition size is exceeding total image size"""
        partitionSizeSum = 0
        for partitions in partitionsDom:
            partition = partitions.getElementsByTagName("partition")
            for p in partition:
                sizeString = p.getAttribute("size")
                sizeNumber = sizeString[0:-1]
                if not (self.rbfUtils.isSizeInt(sizeNumber)):
                    logging.error("Parititon Size Error. Only Integers with suffix G or M allowed. You Specified " + sizeString)
                    sys.exit(BoardTemplateParser.PARTITION_SIZES_ERROR)                        
                size = self.rbfUtils.getImageSizeInM(sizeString)
                sizeSuffix=size[-1:]
                if not (sizeSuffix=="M" or sizeSuffix=="G"):
                    logging.error("Parititon Size Error. Only Integers with suffix G or M allowed. You Specified " + sizeString)
                    sys.exit(BoardTemplateParser.PARTITION_SIZES_ERROR)
                if p.getAttribute("type") == "extended":
                    continue    
                partitionSizeSum = partitionSizeSum + int(size[0:-1])
        logging.info("Image Size: " + self.imageSize + " Parititon Size Sum: " + str(partitionSizeSum)+"M")
        if int(self.imageSize[0:-1]) >= partitionSizeSum:
            return True
        else:
            return False
    
    def createPartitions(self):
        """Creates Partitions"""
        logging.info("Creating Partitions")
        try:
            partitionsDom = self.boardDom.getElementsByTagName("partitions")
        except:
            logging.error("No Partitions Found")
       
        if not self.verifyPartitionSizes(partitionsDom):
            logging.error("Parititon Sizes Exceed Image Size")
            sys.exit(BoardTemplateParser.PARTITION_SIZES_ERROR)
            
        partedString = "parted " + self.imagePath + " -s mklabel msdos "
        extendedStart = False
        totalPartitionCount = 0
        begin = self.rbfUtils.PARTITION_BEGIN
        for partitions in partitionsDom:
            partition = partitions.getElementsByTagName("partition")
            primaryCount = 0
            for p in partition:
                partuuid = str(uuid.uuid4())
                if p.hasAttribute("index") and p.hasAttribute("size") and p.hasAttribute("type") and p.hasAttribute("fs") and p.hasAttribute("mountpoint"):
                    index = p.getAttribute("index")
                    size = self.rbfUtils.getImageSizeInM(p.getAttribute("size"))
                    ptype = p.getAttribute("type")
                    fs = p.getAttribute("fs")
                    mountpoint = p.getAttribute("mountpoint")                                        
                    
                    if fs == "vfat":
                        partuuid = partuuid.upper()[:8]
                    
                    if (ptype =="primary" or ptype == "extended") and totalPartitionCount == 4:
                        logging.error("Cannot Have More Than 4 Primary Partitions")
                        sys.exit(BoardTemplateParser.TOTAL_PARTITIONS_ERROR)
                    if ptype == "primary":
                        primaryCount = primaryCount + 1
                    if ptype == "primary" or ptype == "extended":
                        totalPartitionCount = totalPartitionCount + 1
                    
                    """Adjust partition indexes. parted seems to skip a partition number if a logical partition is create before 3 primary ones"""
                    if primaryCount < 3 and extendedStart == True:
                        index = str(int(index) + 1)
                        
                    logging.info("Creating Partition " + index + " " + size + " " + ptype + " " + fs + " " + mountpoint + " " + partuuid)
                    x = [index, size, begin, ptype, fs, mountpoint, partuuid]
                    self.imageData.append(x)
                    
                    end = self.rbfUtils.calcParitionEndSize(begin,size)
                    
                    if fs == "swap":
                        fs = "linux-swap"
                    elif fs == "vfat":
                        fs = "fat32"
                    partedString = partedString + "mkpart " + ptype + " " + fs + " " + begin[0:-1] + " " + end[0:-1] + " "
                    
                    if ptype == "logical" and extendedStart == False:
                        logging.error("Cannot Create Logical Parititon before Extended")
                        sys.exit(BoardTemplateParser.LOGICAL_PART_ERROR)
                    if ptype == "primary" and extendedStart == True:
                        logging.error("Cannot Create Primary Parititon after Extended")
                        sys.exit(BoardTemplateParser.PRIMARY_PART_ERROR)
                    elif ptype == "extended":
                        extendedStart = True
                    else:
                        begin = end
                else:
                    logging.error("Invalid Partition Data")
                    sys.exit(BoardTemplateParser.INVALID_PARTITION_DATA)
            self.rbfScript.write("echo [INFO ]   $0 Creating Parititons\n")
            self.rbfScript.write(partedString + " &>> rbf.log \n")
            self.rbfScript.write(self.getShellExitString(BoardTemplateParser.PARTED_ERROR))

    def delDeviceIfExists(self, device):
        """Generates command to detach loop device if it exists"""
        return "[ -b " + device + " ] && losetup -d " + device + " &>> rbf.log \nsleep 2\n"

    def createFilesystems(self):
        """Creates Filesystem"""
        self.rbfScript.write("losetup " + self.loopDevice + " " + self.imagePath + "\n")
        self.rbfScript.write("partprobe " + self.loopDevice + "\nsleep 2\n")
        for i in range(0, len(self.imageData)):
            if self.imageData[i][BoardTemplateParser.PTYPE] == "extended":
                continue
            fs = self.imageData[i][BoardTemplateParser.FS]
            index = self.imageData[i][BoardTemplateParser.INDEX]
            partuuid = self.imageData[i][BoardTemplateParser.UUID]
            ptype = self.imageData[i][BoardTemplateParser.PTYPE]

            size = self.rbfUtils.getImageSizeInM(self.imageData[i][BoardTemplateParser.SIZE])
            begin = self.rbfUtils.getImageSizeInM(self.imageData[i][BoardTemplateParser.BEGIN])
            
            self.rbfScript.write("[ -b " + self.loopDevice + "p" + index + " ] && echo [INFO ]   $0 Creating Filesystem " + fs + " on partition " + index + " || exit " + str(BoardTemplateParser.PARTITION_DOES_NOT_EXIST) + "\n")
            
            if fs == "vfat":
                if not checkCommandExistsAccess(['mkfs.vfat']):
                    logging.error("Please Install mkfs.vfat")
                    sys.exit(BoardTemplateParser.SYS_MKFS_COMMANDS_NOT_FOUND)                                    
                self.rbfScript.write("mkfs.vfat -n " + partuuid + " " + self.loopDevice + "p"+ index + " &>> rbf.log \n")
            elif fs == "swap":
                if not checkCommandExistsAccess(['mkswap']):
                    logging.error("Please Install mkswap")
                    sys.exit(BoardTemplateParser.SYS_MKFS_COMMANDS_NOT_FOUND)
                self.rbfScript.write("mkswap -U " + partuuid + " " + self.loopDevice + "p" + index +" &>> rbf.log \n")
            else:
                if not checkCommandExistsAccess(['mkfs.'+fs]):
                    logging.error("Please Install mkfs."+fs)
                    sys.exit(BoardTemplateParser.SYS_MKFS_COMMANDS_NOT_FOUND)
                self.rbfScript.write("mkfs." + fs + " -U " + partuuid + " " + self.loopDevice + "p" + index + " &>> rbf.log \n")    
                
    def mountPartitions(self):
        """Mounting Partitions"""
        logging.info("Mounting Partitions")
        self.rbfScript.write("mkdir -p " + self.workDir + "\n")
        for i in range(0, len(self.imageData)):
                index = self.imageData[i][BoardTemplateParser.INDEX]
                mountpoint = self.imageData[i][BoardTemplateParser.MOUNTPOINT]
                begin = self.imageData[i][BoardTemplateParser.BEGIN]
                fs = self.imageData[i][BoardTemplateParser.FS]
                if mountpoint == "/":
                    logging.info("Mounting Parititon "+ index + " on " + self.workDir + mountpoint)
                    self.rbfScript.write("echo [INFO ]   $0 Mouting Parititon " + index + " on " + mountpoint+"\n")
                    self.rbfScript.write("mount " + self.loopDevice + "p" + index +" " +self.workDir + mountpoint + "\n")
                    self.rbfScript.write(self.getShellExitString(BoardTemplateParser.MOUNTING_ERROR))
                    for j in range(0, len(self.imageData)):
                        pm = self.imageData[j][BoardTemplateParser.MOUNTPOINT]
                        if pm != "/" and pm != "swap":                            
                            self.rbfScript.write("mkdir -p " + self.workDir + mountpoint + pm + "\n")
                            
                    
        for i in range(0, len(self.imageData)):
                if self.imageData[i][BoardTemplateParser.PTYPE] == "extended":
                    continue
                index = self.imageData[i][BoardTemplateParser.INDEX]
                mountpoint = self.imageData[i][BoardTemplateParser.MOUNTPOINT]
                begin = self.imageData[i][BoardTemplateParser.BEGIN]
                fs = self.imageData[i][BoardTemplateParser.FS]
                ptype = self.imageData[i][BoardTemplateParser.PTYPE]
                if mountpoint != "/" and mountpoint !="swap":
                    logging.info("Mounting Parititon "+ index + " on " + self.workDir + mountpoint)
                    self.rbfScript.write("echo [INFO ]   $0 Mouting Parititon " + index + " on " + mountpoint+"\n")
                    self.rbfScript.write("mount " + self.loopDevice + "p" + index +" " +self.workDir + mountpoint + "\n")
                    self.rbfScript.write(self.getShellExitString(BoardTemplateParser.MOUNTING_ERROR))
        
        self.rbfScript.write("mkdir " + self.workDir + "/proc " + self.workDir + "/sys\n")
        self.rbfScript.write("mount -t proc proc " + self.workDir + "/proc\n")
        
    def writeRepos(self):
        """Writes Repos to /etc/yum.repos.d"""
        self.rbfScript.write("rm -rf " + self.workDir + "/etc/yum.repos.d\n")
        self.rbfScript.write("mkdir -p " + self.workDir + "/etc/yum.repos.d\n")
        try:            
            self.reposDom = self.boardDom.getElementsByTagName("repos")
            for repos in self.reposDom:
                repo = repos.getElementsByTagName("repo")
                for r in repo:                    
                    name = r.getAttribute("name")
                    path = r.getAttribute("path")
                    self.repoNames.append(name)
                    logging.info("Found Repo: " + name + " " + path)
                    repoString = "cat > " + self.workDir + "/etc/yum.repos.d/" + name + ".repo << EOF\n"
                    repoString = repoString + "["+name+"]\n"
                    repoString = repoString + "name="+name+"\n"
                    repoString = repoString + "baseurl="+path+"\n"
                    repoString = repoString + "gpgcheck=0\nenabled=1\n"
                    repoString = repoString + "EOF\n"
                    self.rbfScript.write(repoString)
                    self.rbfScript.write(self.getShellExitString(BoardTemplateParser.WRITE_REPO_ERROR))
        except:
            logging.error("Distro Repository Information Incorrect")
            sys.exit(BoardTemplateParser.INCORRECT_REPOSITORY)
        
    def generatePackageString(self, packageList):
        """Generates String from supplied List"""
        packageString = ""
        for p in packageList:
            packageString = p + ' ' + packageString
        return packageString
                
    def installPackages(self):
        """Installing Packages"""
        try:
            packagesDom = self.boardDom.getElementsByTagName("packages")
        except:
            logging.error("No Packages Supplied. Please Fix Template")
            sys.exit(BoardTemplateParser.NO_PACKAGES)
            
        for packageElement in packagesDom:
            try:
                groupPackageString = packageElement.getElementsByTagName('group')[0].childNodes[0].data
            except:
                groupPackageString = ""    
            p = groupPackageString.split(',')
            for i in range(0,len(p)):
                self.packageGroups.append(p[i])
            
            try:    
                packageString = packageElement.getElementsByTagName('package')[0].childNodes[0].data
            except:
                packageString = ""    
            p = packageString.split(',')
            for i in range(0,len(p)):
                self.packages.append(p[i])
        
        packageGroupsString = self.generatePackageString(self.packageGroups).strip()
        packagesString = self.generatePackageString(self.packages).strip()
        logging.info("Installing Package Groups: " + packageGroupsString)        
        logging.info("Installing Packages: " + packagesString)
        
        repoEnableString = "--disablerepo=* --enablerepo="
        for r in self.repoNames:
            repoEnableString = repoEnableString + r + ","
        self.rbfScript.write("rpm --root " + self.workDir + " --initdb\n")
        self.rbfScript.write(self.getShellExitString(BoardTemplateParser.RPMDB_INIT_ERROR))
        if len(packageGroupsString) > 0:
           self.rbfScript.write("echo [INFO ]  $0 Installing Package Groups. Please Wait\n")
           self.rbfScript.write("yum "+ repoEnableString[0:-1] + " --installroot=" + self.workDir + " groupinstall " + packageGroupsString+" 2>> rbf.log\n")
           self.rbfScript.write(self.getShellErrorString(BoardTemplateParser.GROUP_INSTALL_ERROR))
           
        if len(packagesString) > 0:
            self.rbfScript.write("echo [INFO ]  $0 Installing Packages. Please Wait\n")
            self.rbfScript.write("yum "+ repoEnableString[0:-1] + " --installroot=" + self.workDir + " install " + packagesString+" 2>> rbf.log\n")
            self.rbfScript.write(self.getShellErrorString(BoardTemplateParser.PACKAGE_INSTALL_ERROR))
    
    def installKernel(self):
        """Installing Kernel"""
        if self.ubootPath != "none" and not os.path.exists(self.ubootPath):
            logging.error("Could Not Find uboot in:" + self.ubootPath)
            sys.exit(BoardTemplateParser.NO_UBOOT)
        logging.info("Installing Kernel")
        kernelDom = self.boardDom.getElementsByTagName("kernel")
        for k in kernelDom:
            if k.hasAttribute("type"):
                self.kernelType = k.getAttribute("type")
                logging.info("Kernel Type: " + self.kernelType)
            else:
                logging.error("No Kernel Type Specified")
                sys.exit(BoardTemplateParser.NO_KERNEL_TYPE)
        
        if self.kernelType == "custom":
            for k in kernelDom:
                self.kernelPath = k.getElementsByTagName('image')[0].childNodes[0].data
                self.initrdPath = k.getElementsByTagName('initrd')[0].childNodes[0].data
                self.dtbDir = k.getElementsByTagName('dtbdir')[0].childNodes[0].data
                self.dtbFile = k.getElementsByTagName('dtb')[0].childNodes[0].data
                modulesPath = k.getElementsByTagName('modules')[0].childNodes[0].data
                logging.info("Using Custom Kernel: " + self.kernelPath)
                logging.info("Using Initrd: " + self.initrdPath)
                logging.info("Using Modules: " + modulesPath)
                logging.info("Using DTP Dir: " + self.dtbDir)
                logging.info("Using DTB: " + self.dtbFile)
                self.rbfScript.write("cp -rv " + self.kernelPath + " " + self.initrdPath + " " + self.dtbDir + " " + self.workDir + "/boot &>> rbf.log \n")
                self.rbfScript.write(self.getShellExitString(BoardTemplateParser.COPY_KERNEL_ERROR))
                self.rbfScript.write("mkdir -p " + self.workDir + "/lib/modules &>> rbf.log \n")
                self.rbfScript.write(self.getShellExitString(BoardTemplateParser.COPY_KERNEL_ERROR))
                self.rbfScript.write("cp -rv " + modulesPath + " " + self.workDir + "/lib/modules/" + " &>> rbf.log \n")
                self.rbfScript.write(self.getShellExitString(BoardTemplateParser.COPY_KERNEL_ERROR))
        elif self.kernelType == "stock":
            for k in kernelDom:                
                logging.info("Using Stock Kernel")
                self.packages.append('kernel')
                #Required for generation of generic initramfs
                self.packages.append('dracut-config-generic')
        elif self.kernelType == "none":
            logging.info("Not Installing Any Kernel")
        
        if self.firmwareDir != "none" and not os.path.exists(self.firmwareDir):
            logging.error("Could Not Find Firmware in:" + self.firmwareDir)
            sys.exit(BoardTemplateParser.NO_FIRMWARE_FOUND)
            
        if self.firmwareDir != "none":
            self.rbfScript.write("mkdir -p " + self.workDir + "/lib/firmware &>> rbf.log \n")
            self.rbfScript.write(self.getShellExitString(BoardTemplateParser.COPY_FIRMWARE_ERROR))
            self.rbfScript.write("cp -rv " + self.firmwareDir + "/* " + self.workDir + "/lib/firmware &>> rbf.log \n")
            self.rbfScript.write(self.getShellExitString(BoardTemplateParser.COPY_FIRMWARE_ERROR))
            
    def createInitramfs(self):
        """Creates Initramfs for stock kernel"""
        self.initramfsScript = open("initramfs.sh","w")
        if self.kernelType == "stock":
            logging.info("Creating Initramfs")
            if not os.path.exists(self.workDir+"/lib/modules"):
                logging.info("No Kernels Found")
                self.stockKernels = []
                return
            self.stockKernels = os.listdir(self.workDir+"/lib/modules")
            for kernelVer in self.stockKernels:
                self.initramfsScript.write("echo [INFO ]  $0 Creating Initramfs\n")                
                self.initramfsScript.write("chroot "+ self.workDir + " /usr/bin/dracut --no-compress -f /boot/initramfs-" + kernelVer + ".img " + kernelVer + " &>> rbf.log\n")
    
    def finalActions(self):
        """Sets Hostname, Root Pass, SELinux Status & runs Board Script & Finalize Script"""
        hostnameConfig = open(self.etcOverlay+"/hostname","w")
        hostnameConfig.write(self.hostName)
        hostnameConfig.close()
        
        logging.info("Copying Etc Overlay: " + self.etcOverlay)
        self.rbfScript.write("cp -rpv "+ self.etcOverlay + " " + self.workDir+" &>> rbf.log \n")
        self.rbfScript.write(self.getShellExitString(BoardTemplateParser.ETC_OVERLAY_ERROR))
        
        logging.info("Setting empty root pass")
        self.rbfScript.write("sed -i 's/root:x:/root::/' " + self.workDir + "/etc/passwd  &>> rbf.log \n")
        self.rbfScript.write(self.getShellErrorString(BoardTemplateParser.ROOT_PASS_ERROR))
        
        logging.info("Setting SELinux status to " + self.selinuxConf)
        self.rbfScript.write("sed -i 's/SELINUX=enforcing/SELINUX=" + self.selinuxConf + "/' " + self.workDir + "/etc/selinux/config  &>> rbf.log \n")
        self.rbfScript.write(self.getShellErrorString(BoardTemplateParser.SELINUX_ERROR))
        
        if os.path.isfile("boards.d/"+self.boardName+".sh"):
            logging.info("Board Script: " + "boards.d/"+self.boardName+".sh")
            self.rbfScript.write("echo [INFO ]  $0 Running Board Script: " + "boards.d/"+self.boardName+".sh\n")
            self.rbfScript.write("./boards.d/" + self.boardName + ".sh " + self.imagePath + " " + self.ubootPath  + " " + self.workDir + " " + self.rootFiles + "\n")
            self.rbfScript.write(self.getShellExitString(BoardTemplateParser.BOARD_SCRIPT_ERROR))
        
        logging.info("Finalize Script: " + self.finalizeScript)
        self.rbfScript.write("echo [INFO ]  $0 Running Finalize Script: " + self.finalizeScript +"\n")
        self.rbfScript.write(self.finalizeScript+"\n")
        self.rbfScript.write(self.getShellExitString(BoardTemplateParser.FINALIZE_SCRIPT_ERROR))
        self.rbfScript.write("exit 0\n")
        self.rbfScript.close()
    
    def getPartition(self,mountpoint):
        """Gets Partition UUID/LABEL From Dict"""
        for i in range(0,len(self.imageData)):
            if self.imageData[i][BoardTemplateParser.MOUNTPOINT] == mountpoint:
                if self.imageData[i][BoardTemplateParser.FS] == "vfat":
                    return "LABEL="+self.imageData[i][BoardTemplateParser.UUID]
                else:
                    return "UUID=" + self.imageData[i][BoardTemplateParser.UUID]
                
    def getBootPath(self,path):
        """Returns Path for extlinux.conf"""   
        if "/" not in path:
            bootPath = "/" + path
        else:
            bootPath = path[path.rfind("/"):]
        return bootPath
            
    def extLinuxConf(self):
        """Creating extlinux.conf"""
        if self.extLinuxConf == "false":
            self.initramfsScript.close()
            return

        self.initramfsScript.write("mkdir " + self.workDir +"/boot/extlinux\n")
        self.initramfsScript.write(self.getShellExitString(BoardTemplateParser.EXTLINUXCONF_ERROR))
        
        extlinuxContents = "#Created by RootFS Build Factory\nui menu.c32\nmenu autoboot " + self.linuxDistro + "\nmenu title " + self.linuxDistro +" Options\n#menu hidden\ntimeout 60\ntotaltimeout 600\n"
        if self.kernelType == "custom":
            logging.info("Creating extlinux.conf in " + self.workDir +"/boot/extlinux" )
            bootKernelPath = self.getBootPath(self.kernelPath)
            if len(self.initrdPath)!=0:
                bootInitrdPath = self.getBootPath(self.initrdPath)
            else:
                bootInitrdPath = ""
            bootFdtdir = self.getBootPath(self.dtbDir)           
                            
            extlinuxContents = extlinuxContents + "label " + self.linuxDistro + "\n\t" + "kernel " + bootKernelPath +"\n\tappend enforcing=0 root=" + self.getPartition("/") +"\n\t" + "fdtdir " + bootFdtdir +"\n"
            if bootInitrdPath != "none":
                extlinuxContents = extlinuxContents + "\tinitrd " + bootInitrdPath + "\n"
            self.initramfsScript.write ("cat > " + self.workDir +"/boot/extlinux/extlinux.conf << EOF\n" + extlinuxContents + "EOF\n")
            self.initramfsScript.write(self.getShellExitString(BoardTemplateParser.EXTLINUXCONF_ERROR))
        elif self.kernelType == "stock":
            for kernelVer in self.stockKernels:
                extlinuxContents = extlinuxContents + "label " + self.linuxDistro + "\n\t" + "kernel /vmlinuz-" + kernelVer + "\n\tappend enforcing=0 root=" + self.getPartition("/") + "\n\tfdtdir /dtb-" + kernelVer + "\n\tinitrd /initramfs-" + kernelVer + ".img\n\n"
            self.initramfsScript.write ("cat > " + self.workDir +"/boot/extlinux/extlinux.conf << EOF\n" + extlinuxContents + "EOF\n")
            self.initramfsScript.write(self.getShellExitString(BoardTemplateParser.EXTLINUXCONF_ERROR))
            
        self.initramfsScript.close()
            
    def makeBootable(self):
        """Creates /etc/fstab"""
        if not os.path.exists(self.etcOverlay):
            logging.error("Need Etc Overlay To Continue")
            sys.exit(BoardTemplateParser.NO_ETC_OVERLAY)
        try:
            fstab = open(self.etcOverlay+"/fstab","w")
        except:
            logging.error("Could Not Create fstab")
            sys.exit(BoardTemplateParser.FSTAB_ERROR)
            
        fstab.write("#Generated by RootFS Build Factory\n")
        for i in range(0,len(self.imageData)):
            if self.imageData[i][BoardTemplateParser.PTYPE] == "extended":
                continue
            partuuid = self.imageData[i][BoardTemplateParser.UUID]
            mountpoint = self.imageData[i][BoardTemplateParser.MOUNTPOINT]
            partitionPath = self.getPartition(mountpoint)
            fs = self.imageData[i][BoardTemplateParser.FS]
            fstab.write(partitionPath + " " + mountpoint + " " + fs + " noatime 0 0\n")
        fstab.close()
    
    def configureNetwork(self):
        """Configure Network"""
        logging.info("Reading Network Config")
        try:
            networkDom = self.boardDom.getElementsByTagName("network")
        except:
            logging.error("No Network Config Found")
            return
       
        networkConfigPath = self.etcOverlay+"/sysconfig/network-scripts"
        try:
            os.makedirs(networkConfigPath)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(networkConfigPath):
                pass
            else:
                raise
                
        for n in networkDom:
            interface = n.getElementsByTagName("interface")
            for i in interface:
                name = i.getAttribute("name")
                config = i.getAttribute("config")
                logging.info("Found Network Interface: " + name + " " + config)
                if config == "static":
                    ipaddress = i.getElementsByTagName("ipaddress")[0].childNodes[0].data
                    subnetmask = i.getElementsByTagName("subnetmask")[0].childNodes[0].data
                    gateway = i.getElementsByTagName("gateway")[0].childNodes[0].data
                    nameserver = i.getElementsByTagName("nameserver")[0].childNodes[0].data
                    logging.info("IP Addres: " + ipaddress)
                
                    ifcfg = open (networkConfigPath+"/ifcfg-"+name,"w")
                    ifcfg.write("DEVICE=" + name + "\nBOOTPROTO=static\nNM_CONTROLLED=no\nONBOOT=yes\nIPADDR=" + ipaddress +"\nNETMASK=" + subnetmask + "\nGATEWAY=" + gateway+"\n")
                    ifcfg.close()
                    ifcfg = open (self.etcOverlay + "/resolv.conf", "a")
                    ifcfg.write("nameserver " + nameserver+"\n")
                    ifcfg.close()
                else:
                    logging.info("IP Address: DHCP")
                    ifcfg = open (networkConfigPath+"/ifcfg-"+name,"w")
                    ifcfg.write("DEVICE=" + name + "\nBOOTPROTO=dhcp\nNM_CONTROLLED=no\nONBOOT=yes\n")
                    ifcfg.close()
        
    def cleanUp(self):
        """CleanUp Steps"""
        logging.info("Clean Up")
        self.cleanupScript = open("cleanup.sh","w")
        for i in range(0,len(self.imageData)):
            if self.imageData[i][BoardTemplateParser.PTYPE] == "extended":
                continue
            if self.imageData[i][BoardTemplateParser.MOUNTPOINT] != "/" and self.imageData[i][BoardTemplateParser.MOUNTPOINT] != "swap":
                self.cleanupScript.write("umount " + self.workDir + self.imageData[i][BoardTemplateParser.MOUNTPOINT]+"\n")

        self.cleanupScript.write("umount " + self.workDir + "/proc\n")
        self.cleanupScript.write("umount " + self.workDir + "\n")
        self.cleanupScript.write(self.delDeviceIfExists(self.loopDevice))
        self.cleanupScript.write("exit 0\n")
        self.cleanupScript.close()
        if self.action == "build":
            cleanupRet = subprocess.call(["/usr/bin/bash", "cleanup.sh"])
            if cleanupRet != 0:
                logging.error (boardParser.RbfScriptErrors[cleanupRet])
                sys.exit(BoardTemplateParser.CLEANUP_ERROR)
        logging.info("If you need any help, please provide rbf.log rbf.sh initramfs.sh cleanup.sh " + self.xmlTemplate + " and the above output.")

        
if ( __name__ == "__main__"): 
    initLogging()
    if os.getuid() != 0:
        logging.error("You need to be root to use RootFS Build Factory")
        sys.exit(BoardTemplateParser.NOT_ROOT)
        
    if len(sys.argv) != 3:
        printUsage()
        sys.exit(BoardTemplateParser.INCORRECT_ARGUMENTS)
          
    action = sys.argv[1]
    xmlTemplate = sys.argv[2]
    
    if not os.path.exists(xmlTemplate):
        logging.error("XML Template Not Found: " + xmlTemplate)
        sys.exit(BoardTemplateParser.TEMPLATE_NOT_FOUND)
        
    if action == "build" and not platform.uname()[5].startswith("arm"):
        logging.error("This script is not meant to be run on " + platform.uname()[5])
        
    
        
    if checkCommandExistsAccess(['echo', 'fallocate','parted','read','losetup','mount','mkdir','rm','cat','cp','rpm','yum','sed','chroot','partprobe']):
        logging.info("All Commands Found. Continuing")
    else:
        logging.error("Cannot Continue")
        sys.exit(BoardTemplateParser.COMMANDS_NOT_FOUND)
    
    if sys.argv[1] == "parse" or sys.argv[1] == "build":
        logging.info("Arguments Correct. Continuing")
    else:
        printUsage()
        sys.exit(BoardTemplateParser.INCORRECT_ARGUMENTS)    
    
    boardParser = BoardTemplateParser(action, xmlTemplate)
    boardParser.parseTemplate()
    boardParser.createImage()
    boardParser.createPartitions()
    boardParser.createFilesystems()
    boardParser.mountPartitions()
    boardParser.writeRepos()
    boardParser.installKernel()
    boardParser.installPackages()
    boardParser.makeBootable()
    #boardParser.configureNetwork()
    boardParser.finalActions()    
    
    if action == "build":
        logging.info("Running RootFS Build Factory script")
        rbfRet = subprocess.call(["/usr/bin/bash", "rbf.sh"])
        if rbfRet == 0:
            logging.info("Successfully Executed rbf.sh")
        else:
            logging.info("rbf Exit Code: " + str(rbfRet))
            logging.error (boardParser.RbfScriptErrors[rbfRet])
            boardParser.cleanUp()
            sys.exit(rbfRet)
            
        boardParser.createInitramfs()    
        boardParser.extLinuxConf()
        initramfsRet = subprocess.call(["/usr/bin/bash", "initramfs.sh"])
        if initramfsRet != 0:                    
            logging.error(boardParser.RbfScriptErrors[initramfsRet])
            boardParser.cleanUp()
            sys.exit(rbfRet)
        
    boardParser.cleanUp()
    sys.exit(0)
    
