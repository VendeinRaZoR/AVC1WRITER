#!/bin/bash

#spacing
spacing="\n#############################################################################################################\n"

#errors
error="Error:"
fnerror="$spacing $error No filename in argument.\n Use AVC1WRITER.sh <filename>.\n $spacing"
fexerror="$spacing $error AVC File '$1' doesn't have an *.avc extention.\n Check for extention in <filename> field.\n $spacing"
fexsterror="$spacing $error AVC File '$1' doesn't exists.\n Check <filename> field.\n $spacing"
avchferror="$spacing $error AVC File $1 doesn't have correct header format for AVC1READER.\n Check AVC file for errors.\n $spacing"
avcfferror="$spacing $error AVC File $1 doesn't have correct vectors format for AVC1READER.\n Check AVC file for errors.\n $spacing"
nosgnlerror="$spacing $error AVC File $1 doesn't have any signals.\n Check AVC file for at least 1 signal in header.\n $spacing"
nodevice="$spacing $error No SD Device.\n Try to choose correct device if it present.\n $spacing"
formaterror="$spacing $error SD format not done.\n Maybe you have opened files on SD card.\n $spacing"
sdcardnotmounted="$spacing $error SD card not mounted.\n Try to open SD card directory and PRESS ENTER.\n $spacing"
nosdcarderror="$spacing $error No SD Card or another device in system FAT32 formatted.\n Insert SD Card and PRESS ENTER\n $spacing"

#warnings
warning="Warning:"
nosgnlwarning="$spacing $warning AVC File $1 doesn't have any vectors.\n Check AVC file for at least 1 vector.\n $spacing"

#info
info="Info:"
openfileinfo="$spacing $info Opening and finalize AVC File.\n Please Wait ...\n $spacing"
opensdinfo="$spacing $info Now Mount or Reconnect and Open directory your SD card.\n And PRESS ENTER.\n $spacing"
alldoneinfo="$spacing $info Writing done !\n Now you can eject your SD card from slot and put it into AVC1READER slot !\n $spacing"

#avcfilecheck extention
fexcheck=$(echo "$1" | awk '/.avc/')

function avccheckheader {
  read header
  format=$(echo $header | awk '{print $1}')
  if [ "$format" = "FORMAT" ]
  then
    signal0=$(echo $header | awk '{print $2}')
    if [ -n "$signal0" ]
    then
      return
    else
      printf "$nosgnlerror"
    fi
  else
    printf "$avchferror"
  fi
}

function manualmount {
  read
  sdpath=$(mount | grep $sddev | awk '{print $3}')
  if [ -n "$sdpath" ]
  then
    printf " SD card mounted !\n Trying to copy AVC file on SD card ... Please Wait ...\n"
    return
  else
    printf "$sdcardnotmounted"
    manualmount
  fi
}

function choosesddevice {
  echo " Choose SD Device (number):"
  sddevlst=$(fdisk -l | grep FAT32 | nl | awk '{print "["$1"]"" " $2 " " $7 " " $8}') 
  if [ -z "$sddevlst" ]
  then
    printf " $nosdcarderror"
    read
    choosesddevice
  else
    printf " $sddevlst"
  fi
  printf "\n"
  return
}

function avcfinalize {
  avclpatstring=$(cat "$1" | tail -1 | awk '{print $1 " " $2}')
  avclaststring=$(cat "$1" | tail -1 | sed -e 's/R1/Xx/; s/cyc/XXX/; s/1/x/g; s/0/x/g; s/1/H/g; s/0/L/g; s/z/x/g')
  if [ "$avclpatstring" = "Xx XXX" ]
  then
    return
  else
    printf "\n" >> "$1"
    printf "$avclaststring" >> "$1"
  fi
}

function avcfilewrite {
   read sdnum
   sddev=$(fdisk -l | grep FAT32 | awk 'NR == '$sdnum' {print $1}')
   if [ -n "$sddev" ]
   then
      umount $sddev
      printf " Format $sddev to FAT32 ... Please wait ...\n"
      mkfsdone=$(mkfs.vfat $sddev | grep mkfs.fat )
      if [ -n "$mkfsdone" ]
      then
	printf " Format done!\n"
      else
	printf "$formaterror"
	choosesddevice
	avcfilewrite
      fi
      printf "$opensdinfo"
      manualmount
      cp "$1" $sdpath
      printf "$alldoneinfo"
      return
   else
      printf "$nodevice"
      choosesddevice
      avcfilewrite
   fi
}

if [ -z "$1" ] 
then
  printf "$fnerror"
else
  if [ -n "$fexcheck" ]
  then
    if [ -e "$1" ]
    then
      exec 6<&0
      exec <"$1"
      avccheckheader
      exec 0<&6 6<&-
      printf "$openfileinfo"
      avcsgnlstring=$(cat "$1" | tail -1 | awk '{print $1 " " $2}')
      if [ "$avcsgnlstring" != "Xx XXX" ] && [ "$avcsgnlstring" != "R1 cyc" ] 
      then 
	printf "$nosgnlwarning"
      fi
      avcsgnlfmt=$(cat "$1" | head -2 | awk '{print $1 " " $2}') | tail -1     
      if [ "$avcsgnlstring" == "Xx XXX" ] || [ "$avcsgnlstring" == "R1 cyc" ] 
      then
	avcfinalize "$1"
	choosesddevice
	avcfilewrite "$1"
      else
	printf "$avcfferror"
      fi
    else
      printf "$fexsterror"
    fi
  else
    printf "$fexerror"
  fi
fi
