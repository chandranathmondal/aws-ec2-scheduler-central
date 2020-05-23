var AWS = require('aws-sdk');

var getTag = function (tags, key) {
    var value = null;
    
    tags.forEach(tag => {
        if (tag.Key == key) {
            value = tag.Value;
            return;
        }
    });
    
    return value;
}

var startInstances = function(ec2, instance, date, currentTime, upperLimitTime) {
    var startTime = getTag(instance.Tags, 'auto:StartTime');
    
    if (startTime) {
        if (startTime.search(/^([0-9]|0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]$/) == -1) 
            console.log("Instance (ID: " + instance.InstanceId + ") has invalid 'auto:StartTime' tag value: " + startTime + ".\n");
        else {
            var sTime = new Date(date + ' ' + startTime + ':00');
            
            if (currentTime < sTime && sTime < upperLimitTime) {
                var params = {
                    InstanceIds: [
                        instance.InstanceId
                    ]
                };
                
                ec2.startInstances(params, function(err, data){
                    if (err) console.log(err, err.stack); 
                    else console.log('Instance (' + instance.InstanceId + ') started.'); 
                });
            }
        }
    }
    else console.log("Instance (ID: " + instance.InstanceId + ") has no 'auto:StartTime' tag setup.");
}

var stopInstances = function(ec2, instance, date, currentTime, lowerLimitTime) {
    var stopTime = getTag(instance.Tags, 'auto:StopTime');
    
    if (stopTime) {
        if (stopTime.search(/^([0-9]|0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]$/)) 
            console.log("Instance (ID: " + instance.InstanceId + ") has invalid 'auto:StopTime' tag value: " + stopTime + ".\n");
        else {
            var sTime = new Date(date + ' ' + stopTime + ':00');
            
            
            if (lowerLimitTime < sTime && sTime < currentTime) {
                var params = {
                    InstanceIds: [
                        instance.InstanceId
                    ]
                };
                
                ec2.stopInstances(params, function(err, data) {
                    if (err) console.log(err, err.stack); 
                    else console.log('Instance (' + instance.InstanceId + ') stopped.');
                });
            }
        }
    }
    else console.log("Instance (ID: " + instance.InstanceId + ") has no 'auto:StopTime' tag setup.");
}

exports.handler = (event) => {
    var currentTime = new Date();
    var dateAndTime = currentTime.toISOString().replace(/T/, ' ').replace(/\..+/, '');
    
    console.log('Scheduler triggered at ' + dateAndTime + '.\n');
    
    var params = {
        Filters: [
            {
                Name: 'tag-key',
                Values: ['auto:Schedule']
            }
        ]
    };
    
    var ec2 = new AWS.EC2();
    ec2.describeInstances(params, function(err, data) {
        if (err) console.log(err, err.stack);
        else {
            var date = dateAndTime.split(' ')[0];
            var lowerLimitTime = new Date(currentTime.getTime() - (60000 * (event.IntervalMinutes + 1)));
            var upperLimitTime = new Date(currentTime.getTime() + (60000 * (event.IntervalMinutes + 1)));
            
            data.Reservations.forEach(reservation => {
                reservation.Instances.forEach(instance => {
                    var schedule = getTag(instance.Tags, 'auto:Schedule').toUpperCase();
                    
                    if (schedule == 'ON') {
                        startInstances(ec2, instance, date, currentTime, upperLimitTime);
                        stopInstances(ec2, instance, date, currentTime, lowerLimitTime);
                    }
                    else if (schedule == 'OFF') {
                        console.log('Instance (ID: ' + instance.InstanceId + ') is turned-off for auto-schedule.\n');
                    }
                    else {
                        console.log("Instance (ID: " + instance.InstanceId + ") has invalid 'auto:Schedule' tag value: " + schedule + ".\n");
                    }
                });
            });
        }
    });
};
