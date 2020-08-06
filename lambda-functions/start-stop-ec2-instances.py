import json
import os
import logging
import boto3
import re
from datetime import datetime
from datetime import timedelta
import traceback

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ec2 = boto3.client('ec2')

def get_tag(tags, key, case_sensitive):
    value = None
    
    for tag in tags:
        if case_sensitive:
            if tag['Key'] == key:
                value = tag['Value']
                break
        else:
            if tag['Key'].upper() == key.upper():
                value = tag['Value'].upper()
                break
    
    return value

def start_instance(ec2, instance):
    if instance['State']['Name'] == 'stopping' or instance['State']['Name'] == 'stopped':
        ec2.start_instances(InstanceIds=[instance['InstanceId']])
        logger.info('Instance (' + instance['InstanceId'] + ') started.')
    
def stop_instance(ec2, instance):
    if instance['State']['Name'] == 'pending' or instance['State']['Name'] == 'running':
        ec2.stop_instances(InstanceIds=[instance['InstanceId']])
        logger.info('Instance (' + instance['InstanceId'] + ') stopped.')
    
def try_force_stop(force, region, ec2, instance):
    asg_name = None
    
    if 'Tags' in instance:
        asg_name = get_tag(instance['Tags'], 'aws:autoscaling:groupName', True)
    
    if asg_name:
        logger.info('Instance (' + instance['InstanceId'] + ') is part of Auto-Scaling Group (' + asg_name + ').')
        
        if force:
            autoscaling = boto3.client('autoscaling', region_name=region)
            response = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
            asg = response['AutoScalingGroups'][0]
            
            logger.info('Auto-Scaling Group (' + asg_name + ') current configuration = Minimum Size: ' + str(asg['MinSize']) + ', Desired Capacity: ' + str(asg['DesiredCapacity']) + '.')
            
            if asg['MinSize'] > 0 or asg['DesiredCapacity'] > 0:
                #asg.update_auto_scaling_group(MinSize=0, DesiredCapacity=0)
                logger.info('Auto-Scaling Group (' + asg_name + ') modified configuration = Minimum Size: 0, Desired Capacity: 0.')
    else:
        stop_instance(ec2, instance)

def try_start_instance(ec2, instance, date, current_time, next_trigger_time):
    start_time = get_tag(instance['Tags'], 'auto:start-time-utc', False)
    
    if start_time:
        if re.match(r'^(([0-1]?[0-9])|([2][0-3])):([0-5]?[0-9])(:([0-5]?[0-9]))?$', start_time):
            start_time = datetime.strptime(date + ' ' + start_time, '%Y-%m-%d %H:%M')
            
            if current_time < start_time <= next_trigger_time:
                start_instance(ec2, instance)
        else:
            logger.warn("Instance (ID: " + instance['InstanceId'] + ") has invalid 'auto:start-time-utc' tag value: " + start_time + ".");
    else:
        logger.warn("Instance (ID: " + instance['InstanceId'] + ") has no 'auto:start-time-utc' tag setup.")
        
def try_stop_instance(event, region, ec2, instance, date, current_time, last_trigger_time):
    stop_time = get_tag(instance['Tags'], 'auto:stop-time-utc', False)
    
    if stop_time:
        if re.match(r'^(([0-1]?[0-9])|([2][0-3])):([0-5]?[0-9])(:([0-5]?[0-9]))?$', stop_time):
            stop_time = datetime.strptime(date + ' ' + stop_time, '%Y-%m-%d %H:%M')
            
            if last_trigger_time <= stop_time < current_time:
                try_force_stop(True, region, ec2, instance)
        else:
            logger.warn("Instance (ID: " + instance['InstanceId'] + ") has invalid 'auto:stop-time-utc' tag value: " + stop_time + ".")
            
            if event['ForceStop']:
                try_force_stop(event['SmartStop'], region, ec2, instance)
    else:
        logger.warn("Instance (ID: " + instance['InstanceId'] + ") has no 'auto:stop-time-utc' tag setup.")
        
        if event['ForceStop']:
            try_force_stop(event['SmartStop'], region, ec2, instance)
    
def start_stop_instances(event, current_time, region):
    logger.info('Looking into ' + region + ' region...')
    
    date = current_time.strftime('%Y-%m-%d')
    last_trigger_time = current_time - timedelta(minutes=(event['IntervalMinutes']))
    next_trigger_time = current_time + timedelta(minutes=(event['IntervalMinutes']))
    
    ec2 = boto3.client('ec2', region_name=region)
    response = ec2.describe_instances()
    
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            try:
                schedule = None
                
                if 'Tags' in instance:
                    schedule =  get_tag(instance['Tags'], 'auto:schedule', False)
                
                if schedule == 'ON' or schedule == 'TRUE' or schedule == 'YES':
                    try_start_instance(ec2, instance, date, current_time, next_trigger_time)
                    try_stop_instance(event, region, ec2, instance, date, current_time, last_trigger_time)
                elif schedule == 'OFF' or schedule == 'FALSE' or schedule == 'NO':
                    logger.info('Instance (ID: ' + instance['InstanceId'] + ') is turned-off for auto-schedule.')
                else:
                    if schedule:
                        logger.warn("Instance (ID: " + instance['InstanceId'] + ") has invalid 'auto:schedule' tag value: " + schedule + ".")
                    else:
                        logger.warn("Instance (ID: " + instance['InstanceId'] + ") has no 'auto:schedule' tag setup.")
                    
                    if event['ForceSchedule']:
                        try_force_stop(event['SmartStop'], region, ec2, instance)
            except Exception:
                logger.error('Following error occurred while processing Instance (' + instance['InstanceId'] + '):')
                logger.error(traceback.print_exc())

def handler(event, context):
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    logger.info('Scheduler triggered at ' + current_time + '.');
    
    response = ec2.describe_regions()
    
    for region in response['Regions']:
        start_stop_instances(event, datetime.strptime(current_time, '%Y-%m-%d %H:%M'), region['RegionName'])
        
    return {
        'statusCode': 200,
        'body': json.dumps('Scheduler finished execution.')
    }
