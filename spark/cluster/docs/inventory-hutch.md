
=== Identity ===
$ hostname -f
hutch.tworivers

$ id
uid=1000(jhunt) gid=1000(jhunt) groups=1000(jhunt),4(adm),27(sudo),29(audio),30(dip),46(plugdev),100(users),122(lpadmin),988(docker)

$ uname -a
Linux hutch 6.17.0-1014-nvidia #14-Ubuntu SMP PREEMPT_DYNAMIC Tue Mar 17 19:01:40 UTC 2026 aarch64 aarch64 aarch64 GNU/Linux

$ cat /etc/os-release
PRETTY_NAME="Ubuntu 24.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.4 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo


=== CPU and memory ===
$ lscpu | head -25
Architecture:                            aarch64
CPU op-mode(s):                          64-bit
Byte Order:                              Little Endian
CPU(s):                                  20
On-line CPU(s) list:                     0-19
Vendor ID:                               ARM
Model name:                              Cortex-X925
Model:                                   1
Thread(s) per core:                      1
Core(s) per socket:                      10
Socket(s):                               1
Stepping:                                r0p1
Frequency boost:                         disabled
CPU(s) scaling MHz:                      100%
CPU max MHz:                             3900.0000
CPU min MHz:                             1378.0000
BogoMIPS:                                2000.00
Flags:                                   fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm jscvt fcma lrcpc dcpop sha3 sm3 sm4 asimddp sha512 sve asimdfhm dit uscat ilrcpc flagm sb paca pacg dcpodp sve2 sveaes svepmull svebitperm svesha3 svesm4 flagm2 frint svei8mm svebf16 i8mm bf16 dgh bti ecv afp wfxt
Model name:                              Cortex-A725
Model:                                   1
Thread(s) per core:                      1
Core(s) per socket:                      10
Socket(s):                               1
Stepping:                                r0p1
CPU(s) scaling MHz:                      100%

$ free -h
               total        used        free      shared  buff/cache   available
Mem:           121Gi       3.5Gi       116Gi       5.3Mi       2.4Gi       118Gi
Swap:           15Gi          0B        15Gi


=== Storage ===
$ df -h /
Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1p2  3.7T   89G  3.4T   3% /

$ df -h /srv 2>/dev/null || echo '(no /srv mount)'
Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1p2  3.7T   89G  3.4T   3% /

$ lsblk
NAME        MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
loop0         7:0    0  68.9M  1 loop /snap/core22/2340
loop1         7:1    0     4K  1 loop /snap/bare/5
loop2         7:2    0  61.9M  1 loop /snap/core24/1500
loop3         7:3    0  61.9M  1 loop /snap/core24/1588
loop4         7:4    0 266.1M  1 loop /snap/firefox/8188
loop5         7:5    0  15.6M  1 loop /snap/firmware-updater/227
loop6         7:6    0  15.5M  1 loop /snap/firmware-updater/225
loop7         7:7    0 241.1M  1 loop /snap/firefox/8242
loop8         7:8    0   503M  1 loop /snap/gnome-42-2204/245
loop9         7:9    0 174.6M  1 loop /snap/mesa-2404/1166
loop10        7:10   0 493.6M  1 loop /snap/gnome-42-2204/228
loop11        7:11   0 552.9M  1 loop /snap/gnome-46-2404/154
loop12        7:12   0  91.7M  1 loop /snap/gtk-common-themes/1535
loop13        7:13   0    69M  1 loop /snap/core22/2412
loop14        7:14   0  12.2M  1 loop /snap/snap-store/1217
loop15        7:15   0    10M  1 loop /snap/snap-store/1271
loop16        7:16   0  41.8M  1 loop /snap/snapd/26383
loop17        7:17   0   560K  1 loop /snap/snapd-desktop-integration/359
loop18        7:18   0  42.6M  1 loop /snap/snapd/26869
loop19        7:19   0   560K  1 loop /snap/snapd-desktop-integration/363
loop20        7:20   0 221.2M  1 loop /snap/thunderbird/1072
loop21        7:21   0   221M  1 loop /snap/thunderbird/1045
nvme0n1     259:0    0   3.7T  0 disk 
├─nvme0n1p1 259:1    0   298M  0 part /boot/efi
└─nvme0n1p2 259:2    0   3.7T  0 part /


=== GPU ===
$ nvidia-smi
Tue May  5 10:44:29 2026       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 580.142                Driver Version: 580.142        CUDA Version: 13.0     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GB10                    On  |   0000000F:01:00.0 Off |                  N/A |
| N/A   36C    P8              4W /  N/A  | Not Supported          |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|    0   N/A  N/A            2747      G   /usr/lib/xorg/Xorg                       18MiB |
|    0   N/A  N/A            2911      G   /usr/bin/gnome-shell                      6MiB |
+-----------------------------------------------------------------------------------------+

$ nvidia-smi -L
GPU 0: NVIDIA GB10 (UUID: GPU-b0ec33a0-2589-53de-953c-0713d37d0794)

$ nvidia-smi topo -m
	[4mGPU0	NIC0	NIC1	NIC2	NIC3	CPU Affinity	NUMA Affinity	GPU NUMA ID[0m
GPU0	 X 	NODE	NODE	NODE	NODE	0-19	0		N/A
NIC0	NODE	 X 	PIX	NODE	NODE				
NIC1	NODE	PIX	 X 	NODE	NODE				
NIC2	NODE	NODE	NODE	 X 	PIX				
NIC3	NODE	NODE	NODE	PIX	 X 				

Legend:

  X    = Self
  SYS  = Connection traversing PCIe as well as the SMP interconnect between NUMA nodes (e.g., QPI/UPI)
  NODE = Connection traversing PCIe as well as the interconnect between PCIe Host Bridges within a NUMA node
  PHB  = Connection traversing PCIe as well as a PCIe Host Bridge (typically the CPU)
  PXB  = Connection traversing multiple PCIe bridges (without traversing the PCIe Host Bridge)
  PIX  = Connection traversing at most a single PCIe bridge
  NV#  = Connection traversing a bonded set of # NVLinks

NIC Legend:

  NIC0: rocep1s0f0
  NIC1: rocep1s0f1
  NIC2: roceP2p1s0f0
  NIC3: roceP2p1s0f1


$ nvcc --version 2>/dev/null || echo '(nvcc not in PATH)'
(nvcc not in PATH)


=== Container runtime ===
$ docker --version 2>/dev/null || echo '(docker not installed)'
Docker version 29.2.1, build a5c7197

$ docker info 2>/dev/null | head -40
Client: Docker Engine - Community
 Version:    29.2.1
 Context:    default
 Debug Mode: false
 Plugins:
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.31.1
    Path:     /usr/libexec/docker/cli-plugins/docker-buildx
  compose: Docker Compose (Docker Inc.)
    Version:  v5.0.2
    Path:     /usr/libexec/docker/cli-plugins/docker-compose

Server:
 Containers: 0
  Running: 0
  Paused: 0
  Stopped: 0
 Images: 21
 Server Version: 29.2.1
 Storage Driver: overlay2
  Backing Filesystem: extfs
  Supports d_type: true
  Using metacopy: false
  Native Overlay Diff: true
  userxattr: false
 Logging Driver: json-file
 Cgroup Driver: systemd
 Cgroup Version: 2
 Plugins:
  Volume: local
  Network: bridge host ipvlan macvlan null overlay
  Log: awslogs fluentd gcplogs gelf journald json-file local splunk syslog
 CDI spec directories:
  /etc/cdi
  /var/run/cdi
 Swarm: inactive
 Runtimes: io.containerd.runc.v2 runc
 Default Runtime: runc
 Init Binary: docker-init
 containerd version: dea7da592f5d1d2b7755e3a161be07f43fad8f75

$ (dpkg -l 2>/dev/null | grep -i nvidia-container) || (rpm -qa 2>/dev/null | grep -i nvidia-container) || echo '(no nvidia-container-toolkit packages found)'
ii  libnvidia-container-tools                        1.19.0-1                                         arm64        NVIDIA container runtime library (command-line tools)
ii  libnvidia-container1:arm64                       1.19.0-1                                         arm64        NVIDIA container runtime library
ii  nvidia-container-toolkit                         1.19.0-1                                         arm64        NVIDIA Container toolkit
ii  nvidia-container-toolkit-base                    1.19.0-1                                         arm64        NVIDIA Container Toolkit Base


=== Python ===
$ python3 --version
Python 3.12.3

$ which python3
/usr/bin/python3


=== Network interfaces ===
$ ip -br addr
lo               UNKNOWN        127.0.0.1/8 ::1/128 
enP7s7           UP             192.168.1.163/24 fdfd:7e5a:de0e:42b1:4da8:9b88:d63a:2105/64 fdfd:7e5a:de0e:42b1:b82b:89a6:f06f:130d/64 fdfd:7e5a:de0e:42b1:7e1a:13dc:b862:5b24/64 fe80::e186:fcee:d842:2edb/64 
enp1s0f0np0      DOWN           
enp1s0f1np1      UP             169.254.127.30/16 fe80::4ebb:47ff:fe2f:9113/64 
enP2p1s0f0np0    DOWN           
enP2p1s0f1np1    UP             fe80::fc88:5ca8:11e8:e01b/64 
wlP9s9           DOWN           
docker0          DOWN           172.17.0.1/16 

$ ip -br link
lo               UNKNOWN        00:00:00:00:00:00 <LOOPBACK,UP,LOWER_UP> 
enP7s7           UP             4c:bb:47:2f:91:11 <BROADCAST,MULTICAST,UP,LOWER_UP> 
enp1s0f0np0      DOWN           4c:bb:47:2f:91:12 <NO-CARRIER,BROADCAST,MULTICAST,UP> 
enp1s0f1np1      UP             4c:bb:47:2f:91:13 <BROADCAST,MULTICAST,UP,LOWER_UP> 
enP2p1s0f0np0    DOWN           4c:bb:47:2f:91:16 <NO-CARRIER,BROADCAST,MULTICAST,UP> 
enP2p1s0f1np1    UP             4c:bb:47:2f:91:17 <BROADCAST,MULTICAST,UP,LOWER_UP> 
wlP9s9           DOWN           58:02:05:f5:fb:8c <NO-CARRIER,BROADCAST,MULTICAST,UP> 
docker0          DOWN           aa:ac:e4:c1:87:bd <NO-CARRIER,BROADCAST,MULTICAST,UP> 

$ lspci 2>/dev/null | grep -iE 'mellanox|connectx|ethernet'
0000:01:00.0 Ethernet controller: Mellanox Technologies MT2910 Family [ConnectX-7]
0000:01:00.1 Ethernet controller: Mellanox Technologies MT2910 Family [ConnectX-7]
0002:01:00.0 Ethernet controller: Mellanox Technologies MT2910 Family [ConnectX-7]
0002:01:00.1 Ethernet controller: Mellanox Technologies MT2910 Family [ConnectX-7]
0007:01:00.0 Ethernet controller: Realtek Semiconductor Co., Ltd. Device 8127 (rev 05)


=== Listening ports ===
$ ss -tlnp 2>/dev/null | head -30
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess
LISTEN 0      4096       127.0.0.1:11000      0.0.0.0:*          
LISTEN 0      4096         0.0.0.0:22         0.0.0.0:*          
LISTEN 0      4096       127.0.0.1:631        0.0.0.0:*          
LISTEN 0      4096      127.0.0.54:53         0.0.0.0:*          
LISTEN 0      4096   127.0.0.53%lo:53         0.0.0.0:*          
LISTEN 0      4096           [::1]:631           [::]:*          
LISTEN 0      4096            [::]:22            [::]:*          


=== Firewall ===
$ sudo -n firewall-cmd --state 2>/dev/null || echo '(firewalld not active or no NOPASSWD)'
(firewalld not active or no NOPASSWD)

$ sudo -n ufw status 2>/dev/null || echo '(ufw not active or no NOPASSWD)'
Status: inactive

$ sudo -n iptables -S 2>/dev/null | head -30 || echo '(could not read iptables)'
-P INPUT ACCEPT
-P FORWARD DROP
-P OUTPUT ACCEPT
-N DOCKER
-N DOCKER-BRIDGE
-N DOCKER-CT
-N DOCKER-FORWARD
-N DOCKER-INTERNAL
-N DOCKER-USER
-A FORWARD -j DOCKER-USER
-A FORWARD -j DOCKER-FORWARD
-A DOCKER ! -i docker0 -o docker0 -j DROP
-A DOCKER-BRIDGE -o docker0 -j DOCKER
-A DOCKER-CT -o docker0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A DOCKER-FORWARD -j DOCKER-CT
-A DOCKER-FORWARD -j DOCKER-INTERNAL
-A DOCKER-FORWARD -j DOCKER-BRIDGE
-A DOCKER-FORWARD -i docker0 -j ACCEPT


=== Done ===
