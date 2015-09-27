#!/bin/env php
<?php

$currentPath = getcwd();
$allowInst = array('itac', 'hpctk', 'mpe', 'scal', 'mpip');
$path = stripos($_SERVER['argv'][1], '/') === 0 ? $_SERVER['argv'][1] : getcwd() . DIRECTORY_SEPARATOR . $_SERVER['argv'][1];
$outRanks=array();
$outData = array();

if (($path = realpath($path)) === false) {
    die('Wrong path ' . $_SERVER['argv'][1]);
}

if (is_dir("$path/hpcc")) {
    parse('hpcc');
}
if (is_dir("$path/cpi")) {
    parse('cpi');
}
renderOutData();
exit(0);

function renderOutData()
{
    global $currentPath,$path,$outData,$outRanks;
    chdir($currentPath);
    
    foreach($outData as $app => $appData) {
	renderAppData("stat_$app.csv", $appData);
    }
}

function renderAppData($file, $appData)
{
    global $currentPath,$path,$outData,$outRanks;
    $f = fopen($file, 'w');
    $ranks = array_values($outRanks);
    sort($ranks);
    fputcsv($f, array_merge(array('n'), $ranks), ';');
    foreach ($appData as $inst => $instData) {
	ksort($instData);
        foreach ($instData as $run => $runData) {
    	    $data = array("$inst $run");
    	    foreach ($ranks as $rInd) {
    	        $data[] = array_key_exists($rInd, $runData) ? $runData[$rInd] : '';
    	    }
    	    fputcsv($f, $data, ';');
    	}
    }
    foreach ($appData as $inst => $instData) {
	ksort($instData);
        foreach ($instData as $run => $runData) {
    	    $data = array("$inst $run, MB");
    	    foreach ($ranks as $rInd) {
    	        $data[] = array_key_exists($rInd, $runData) ? $runData[$rInd]/1024/1024 : '';
    	    }
    	    fputcsv($f, $data, ';');
    	}
    }
    fclose($f);
}

function parse($app)
{
    global $path, $allowInst;
    $files = scandir("$path/$app");

    foreach($files as $inst) {
	$instPath = "$path/$app/$inst";
	if (in_array($inst, $allowInst) && is_dir($instPath)) {
	    parseInstrument($app, $inst);
	}
    }
}

function parseInstrument($app, $inst)
{
    global $path;
    echo $app . ' ' . $inst ."\n";

    $instPath = "$path/$app/$inst";
    chdir($instPath);
    $runs = scandir('.');
    foreach ($runs as $run) {
	chdir($instPath);
	if (preg_match('#^r#', $run) && is_dir($run)) {
	    $fname = 'parse' . implode('', array_map('ucfirst', array($inst)));
	    if (is_callable($fname)) {
		$fname("$instPath/$run", $app, $run);
	    } else {
		echo "WARNING: Skip call for App:$app Inst:$inst.\n";
	    }
	}
    }
}

function updateOutData($value, $app, $inst, $run, $ranks)
{
    global $outData, $outRanks;
    $run = preg_replace('/^(r)/', '', $run);
    if (!isset($outData[$app])) $outData[$app] = array();
    if (!isset($outData[$app][$inst])) $outData[$app][$inst] = array();
    if (!isset($outData[$app][$inst][$run])) $outData[$app][$inst][$run] = array();
    $outRanks[$ranks] = $ranks;
    $outData[$app][$inst][$run][$ranks] = $value;
}

function parseItac($in, $app, $run)
{
    global $path, $outData;
    chdir($in);
    $files = scandir('.');
    foreach($files as $ranks) {
        echo '.';
	$ranksPath = "$in/$ranks";
	if (!preg_match('/\d+/', $ranks) || !is_dir($ranksPath)) {
	    continue;
	}
	chdir($ranksPath);
	$itacFiles = scandir(".");
	$total = 0;
	foreach($itacFiles as $f){
	    $rFile = "$ranksPath/$f";
	    if (!in_array($f, array('hpccinf.txt', 'hpccoutf.txt')) && is_file($rFile)) {
		//echo sprintf("$rFile %s\n", filesize($rFile));
		$total += filesize($rFile);
	    }
	}
	if ($total > 0) updateOutData($total, $app, 'itac', $run, $ranks);
    }
    echo "\n";
}

function parseMpip($in, $app, $run)
{
    global $path;
    chdir($in);
    $files = scandir('.');
    foreach($files as $ranks) {
        echo '.';
	$ranksPath = "$in/$ranks";
	if (!preg_match('/\d+/', $ranks) || !is_dir($ranksPath)) {
	    continue;
	}
	chdir($ranksPath);
	$files = scandir(".");
	foreach($files as $f){
	    $rFile = "$ranksPath/$f";
	    if (preg_match('/mpiP$/', $f) && is_file($rFile)) {
		//echo sprintf("$rFile %s\n", filesize($rFile));
		updateOutData(filesize($rFile), $app, 'mpip', $run, $ranks);
		break;
	    }
	}
    }
    echo "\n";
}

function parseScal($in, $app, $run)
{
    global $path;
    chdir($in);
    $files = scandir('.');
    foreach($files as $ranks) {
        echo '.';
	$ranksPath = "$in/$ranks";
	if (!preg_match('/\d+/', $ranks) || !is_dir($ranksPath)) {
	    continue;
	}
	chdir($ranksPath);
	$files = scandir(".");
	foreach($files as $f){
	    $rDir = "$ranksPath/$f";
	    if (preg_match('/^score/', $f) && is_dir($rDir)) {
		//echo sprintf("$rFile %s\n", filesize($rFile));
		$total = 0;
		foreach (scandir("$rDir") as $ff) {
		    $ffPath = "$rDir/$ff";
		    if (is_file($ffPath)) {
			$total += filesize($ffPath);
		    }
		}
		updateOutData($total, $app, 'scal', $run, $ranks);
		break;
	    }
	}
    }
    echo "\n";
}

function parseMpe($in, $app, $run)
{
    global $path;
    chdir($in);
    $files = scandir('.');
    foreach($files as $ranks) {
        echo '.';
	$ranksPath = "$in/$ranks";
	if (!preg_match('/\d+/', $ranks) || !is_dir($ranksPath)) {
	    continue;
	}
	chdir($ranksPath);
	$files = scandir(".");
	foreach($files as $f){
	    $rDir = "$ranksPath/$f";
	    if (preg_match('/clog2$/', $f) && is_file($rDir)) {
		//echo sprintf("$rFile %s\n", filesize($rFile));
		updateOutData(filesize($rDir), $app, 'mpe clog', $run, $ranks);
	    }
	    if (preg_match('/slog2$/', $f) && is_file($rDir)) {
		//echo sprintf("$rFile %s\n", filesize($rFile));
		updateOutData(filesize($rDir), $app, 'mpe slog', $run, $ranks);
	    }
	}
    }
    echo "\n";
}

function parseHpctk($in, $app, $run)
{
    global $path;
    chdir($in);
    $files = scandir('.');
    foreach($files as $ranks) {
        echo '.';
	$ranksPath = "$in/$ranks";
	if (!preg_match('/\d+/', $ranks) || !is_dir($ranksPath)) {
	    continue;
	}
	chdir($ranksPath);
	$files = scandir(".");
	foreach($files as $f){
	    $rDir = "$ranksPath/$f";
	    if (preg_match('/^hpctoolkit/', $f) && is_dir($rDir)) {
		//echo sprintf("$rFile %s\n", filesize($rFile));
		$total = 0;
		foreach (scandir("$rDir") as $ff) {
		    $ffPath = "$rDir/$ff";
		    if (is_file($ffPath)) {
			//echo sprintf("$ffPath %s\n", filesize($ffPath));
			$total += filesize($ffPath);
		    }
		}
		updateOutData($total, $app, 'hpctk', $run, $ranks);
	    }
	}
    }
    echo "\n";
}